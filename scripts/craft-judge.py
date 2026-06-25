#!/usr/bin/env python3
"""craft-judge.py — adversarial craft judge for andremacedo.com (taste layer).

Fresh-eyes verification of CRAFT, the external/adversarial counterpart to the
agent's (untrusted) self-reported craft_check. Feeds the RENDERED screenshot(s)
to gemini-2.5-pro via the local LiteLLM proxy (localhost:4000, no credentials)
with one adversarial job: assume slop until proven otherwise, score against
scripts/craft-rubric.md, and name what is generic/safe/template-grade. It judges
the pixels, never the agent's stated intentions.

Wired into the runner verdict gate in Phase 3: is_slop OR overall < threshold =>
FAILED (fail-closed, working tree reverted, previous deploy stays live), exactly
like a contrast failure. A judge that cannot run is also fail-closed.

Exit codes:  0 = PASS (craft cleared)   1 = FAIL (slop or below threshold)
             2 = ERROR (could not judge — treat as fail-closed at the gate)

Usage:
  craft-judge.py --desktop /tmp/andremacedo-self-desktop.jpg \
                 [--mobile /tmp/andremacedo-self-mobile.jpg] \
                 [--rubric scripts/craft-rubric.md] [--threshold 7.0] \
                 [--model gemini/gemini-2.5-pro] [--json-out PATH] [--quiet]
"""
import argparse, base64, json, os, sys, urllib.request, urllib.error

DEFAULT_URL = "http://localhost:4000/v1/chat/completions"
DEFAULT_MODEL = "gemini/gemini-2.5-pro"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RUBRIC = os.path.join(HERE, "craft-rubric.md")

AXES = ["type_scale", "spacing_system", "focal_hierarchy", "restraint",
        "hero", "composition", "type_craft", "color"]

SYSTEM = (
    "You are an adversarial design-engineering critic with fresh eyes and zero "
    "stake in this page. Assume it is mediocre, default-grade AI slop until the "
    "pixels prove otherwise. Your job is to find what is generic, safe, "
    "derivative, or template-grade and name it specifically. You judge ONLY the "
    "rendered screenshot — never any stated intent, caption, or description. "
    "Vague praise is worthless. 'Clean and inoffensive' is itself the slop and "
    "must FAIL. Be stingy: a high score must be earned by a visible, decisive "
    "aesthetic move a templated generator would not make. Output JSON only — no "
    "prose before or after, no code fences."
)


def b64_data_url(path):
    with open(path, "rb") as f:
        raw = f.read()
    ext = os.path.splitext(path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii"), len(raw)


def build_user_content(rubric, desktop, mobile):
    parts = [{
        "type": "text",
        "text": (
            "Judge this andremacedo.com generation against the rubric below. "
            "andremacedo.com is a living art organism that an AI rebuilds — it is "
            "NOT a SaaS landing page; SaaS-landing shapes are slop here. Primary "
            "judgment is the DESKTOP render. If a mobile render follows, confirm "
            "the craft holds responsively (do not let mobile alone rescue a weak "
            "desktop).\n\nScore every axis 0-10, be stingy, and set is_slop=true "
            "if ANY cardinal slop state in the rubric is present. Return JSON "
            "EXACTLY matching the output contract — keys: axes (the 8 named axes), "
            "overall (number), is_slop (boolean), findings (array of specific "
            "strings), what_works (array, may be empty), reasoning (string).\n\n"
            "===== RUBRIC =====\n" + rubric + "\n===== END RUBRIC =====\n\n"
            "DESKTOP render follows:"
        ),
    }]
    url, _ = b64_data_url(desktop)
    parts.append({"type": "image_url", "image_url": {"url": url}})
    if mobile and os.path.isfile(mobile):
        parts.append({"type": "text", "text": "MOBILE render follows:"})
        murl, _ = b64_data_url(mobile)
        parts.append({"type": "image_url", "image_url": {"url": murl}})
    return parts


def call_proxy(url, model, system, user_content, timeout, retries):
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user_content}],
        "temperature": 0.2,
    }).encode("utf-8")
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001 — proxy/network/parse all fail-closed
            last = e
    raise RuntimeError(f"proxy call failed after {retries} attempt(s): {last}")


def extract_json(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    try:
        return json.loads(t)
    except Exception:
        pass
    # fall back to first balanced {...}
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in model output")
    depth = 0
    for i in range(start, len(t)):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start:i + 1])
    raise ValueError("unbalanced JSON in model output")


def normalize(v):
    axes = {a: float(v.get("axes", {}).get(a, 0) or 0) for a in AXES}
    overall = v.get("overall")
    overall = float(overall) if overall is not None else round(sum(axes.values()) / len(axes), 2)
    return {
        "axes": axes,
        "overall": overall,
        "is_slop": bool(v.get("is_slop", True)),  # default-slop if model omits it
        "findings": [str(x) for x in (v.get("findings") or [])],
        "what_works": [str(x) for x in (v.get("what_works") or [])],
        "reasoning": str(v.get("reasoning", "")),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desktop", required=True)
    ap.add_argument("--mobile")
    ap.add_argument("--rubric", default=DEFAULT_RUBRIC)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--threshold", type=float, default=7.0)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--json-out")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    def emit(verdict, code):
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(verdict, f, indent=2, ensure_ascii=False)
        if not args.quiet:
            print(json.dumps(verdict, indent=2, ensure_ascii=False))
        sys.exit(code)

    if not os.path.isfile(args.desktop):
        emit({"error": f"desktop screenshot missing: {args.desktop}",
              "verdict": "ERROR", "is_slop": True}, 2)
    try:
        rubric = open(args.rubric, encoding="utf-8").read()
    except Exception as e:
        emit({"error": f"rubric unreadable: {e}", "verdict": "ERROR", "is_slop": True}, 2)

    try:
        content = build_user_content(rubric, args.desktop, args.mobile)
        raw = call_proxy(args.url, args.model, SYSTEM, content, args.timeout, args.retries)
        v = normalize(extract_json(raw))
    except Exception as e:  # noqa: BLE001
        emit({"error": str(e), "verdict": "ERROR", "is_slop": True}, 2)

    passed = (not v["is_slop"]) and v["overall"] >= args.threshold
    v["threshold"] = args.threshold
    v["model"] = args.model
    v["verdict"] = "PASS" if passed else "SLOP"
    emit(v, 0 if passed else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""craft-judge.py — DUAL adversarial craft judge for andremacedo.com (taste layer).

Fresh-eyes verification of CRAFT, the external/adversarial counterpart to the
agent's (untrusted) self-reported craft_check. Two INDEPENDENT critics from
DIFFERENT model families judge the same rendered screenshot(s) against the same
rubric — the point is uncorrelated blind spots, not raw capability:

  Critic A = claude-opus-4-8-oauth
  Critic B = grok-4-1-fast-reasoning   (different family)
             fallback gemini-3.5-flash ONLY if B is slow/flaky (never gemini-2.5-pro)

Combination is fail-closed with a MARGIN RULE: SHIP if BOTH critics return
not-slop AND each clears the base threshold (both_passed), OR if exactly ONE
critic passes and its overall clears the higher --margin (margin_override — a
lone STRONG pass overrides the other critic's slop veto). It FAILS when both
flag slop, when the sole passing critic is below the margin, or when a critic
cannot be scored at all (ERROR is never overridden). A FAILED verdict at the
runner gate reverts the working tree and keeps the previous deploy live,
exactly like a contrast failure.

Both judge the SCREENSHOT — never the agent's stated intentions. Model IDs are
verified against the live proxy (curl localhost:4000/v1/models) before wiring,
never assumed from memory.

Exit codes:  0 = PASS (both critics cleared)
             1 = FAIL (either critic flagged slop or scored below threshold)
             2 = ERROR (a critic could not be obtained — fail-closed at the gate)
"""
import argparse, base64, json, os, sys, urllib.request

DEFAULT_URL = "http://localhost:4000/v1/chat/completions"


def proxy_api_key():
    """Bearer key for the local litellm proxy (master-key auth activated
    2026-07-24, quota-governor phase 2). Prefer ~/.openclaw/.env (canonical,
    current) over the process env, which can carry a stale key."""
    env_file = os.path.expanduser("~/.openclaw/.env")
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("LITELLM_MASTER_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return os.environ.get("LITELLM_MASTER_KEY")
CRITIC_A = "claude-opus-4-8-oauth"
CRITIC_B = "grok-4-1-fast-reasoning"
CRITIC_B_FALLBACK = "gemini-3.5-flash"          # never gemini-2.5-pro (deprecated)
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
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


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
    parts.append({"type": "image_url", "image_url": {"url": b64_data_url(desktop)}})
    if mobile and os.path.isfile(mobile):
        parts.append({"type": "text", "text": "MOBILE render follows:"})
        parts.append({"type": "image_url", "image_url": {"url": b64_data_url(mobile)}})
    return parts


def call_proxy(url, model, system, user_content, timeout, retries):
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user_content}],
        "temperature": 0.2,
    }).encode("utf-8")
    last = None
    for _ in range(retries):
        try:
            headers = {"Content-Type": "application/json"}
            key = proxy_api_key()
            if key:
                headers["Authorization"] = f"Bearer {key}"
            req = urllib.request.Request(
                url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001 — proxy/network/parse all fail-closed
            last = e
    raise RuntimeError(f"{model}: proxy call failed after {retries} attempt(s): {last}")


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


def judge_one(url, model, content, timeout, retries):
    """Run a single critic; returns a normalized verdict or raises."""
    return normalize(extract_json(call_proxy(url, model, SYSTEM, content, timeout, retries)))


def critic_passed(v, threshold):
    """A critic passes iff it did NOT flag slop AND cleared the base threshold."""
    return (not v["is_slop"]) and v["overall"] >= threshold


def decide_gate(a, b, threshold, margin):
    """Pure, testable combination rule (the 'margin rule').

    a / b are normalized critic verdicts, or None if a critic could not be
    obtained. Returns a dict: {passed, gate_rule[, override_label, override_overall]}.

      - both_passed    : both critics pass (unchanged happy path)      -> SHIP
      - margin_override: exactly one critic passed AND its overall is   -> SHIP
                         at/above the margin (a lone STRONG pass beats
                         the other critic's slop veto)
      - failed         : anything else                                 -> FAIL

    Fail-closed: if EITHER critic is unobtainable (None), the gate fails and is
    NEVER overridden by the other critic's pass — an ERROR is not a veto that a
    margin can beat, it is an inability to verify craft at all.
    """
    if a is None or b is None:
        return {"passed": False, "gate_rule": "failed"}
    a_pass = critic_passed(a, threshold)
    b_pass = critic_passed(b, threshold)
    if a_pass and b_pass:
        return {"passed": True, "gate_rule": "both_passed"}
    if a_pass ^ b_pass:  # exactly one passed
        label, v = ("A", a) if a_pass else ("B", b)
        if v["overall"] >= margin:
            return {"passed": True, "gate_rule": "margin_override",
                    "override_label": label, "override_overall": v["overall"]}
    return {"passed": False, "gate_rule": "failed"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desktop", required=True)
    ap.add_argument("--mobile")
    ap.add_argument("--rubric", default=DEFAULT_RUBRIC)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--critic-a", default=CRITIC_A)
    ap.add_argument("--critic-b", default=CRITIC_B)
    ap.add_argument("--critic-b-fallback", default=CRITIC_B_FALLBACK)
    ap.add_argument("--threshold", type=float, default=7.0)
    ap.add_argument("--margin", type=float, default=7.3,
                    help="a lone passing critic must clear this (> threshold) to "
                         "override the other critic's slop veto and ship")
    ap.add_argument("--timeout-a", type=float, default=120.0)
    ap.add_argument("--timeout-b", type=float, default=90.0)   # grok reasoning can be slower; beyond this -> fallback
    ap.add_argument("--retries", type=int, default=2)
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
        emit({"verdict": "ERROR", "is_slop": True, "error": f"desktop screenshot missing: {args.desktop}"}, 2)
    try:
        rubric = open(args.rubric, encoding="utf-8").read()
    except Exception as e:
        emit({"verdict": "ERROR", "is_slop": True, "error": f"rubric unreadable: {e}"}, 2)

    content = build_user_content(rubric, args.desktop, args.mobile)

    # Critic A — no fallback; if it cannot be obtained, we cannot verify craft.
    try:
        a = judge_one(args.url, args.critic_a, content, args.timeout_a, args.retries)
        a_model = args.critic_a
    except Exception as e:  # noqa: BLE001
        emit({"verdict": "ERROR", "is_slop": True,
              "error": f"critic A ({args.critic_a}) unobtainable: {e}"}, 2)

    # Critic B — grok; fall back to gemini-3.5-flash ONLY if grok is slow/flaky.
    b_fell_back_from = None
    try:
        b = judge_one(args.url, args.critic_b, content, args.timeout_b, args.retries)
        b_model = args.critic_b
    except Exception as e_b:  # noqa: BLE001
        try:
            b = judge_one(args.url, args.critic_b_fallback, content, args.timeout_a, args.retries)
            b_model = args.critic_b_fallback
            b_fell_back_from = f"{args.critic_b} ({e_b})"
        except Exception as e_fb:  # noqa: BLE001
            emit({"verdict": "ERROR", "is_slop": True,
                  "error": f"critic B unobtainable: {args.critic_b} -> {e_b}; "
                           f"fallback {args.critic_b_fallback} -> {e_fb}"}, 2)

    a_pass, b_pass = critic_passed(a, args.threshold), critic_passed(b, args.threshold)
    # MARGIN RULE: ship if BOTH clear, OR exactly one clears at/above --margin.
    decision = decide_gate(a, b, args.threshold, args.margin)
    passed = decision["passed"]
    gate_rule = decision["gate_rule"]

    def fail_desc(label, model, v):
        why = "slop" if v["is_slop"] else "{}<{}".format(v["overall"], args.threshold)
        return "{}/{}({})".format(label, model, why)

    failers = []
    if not a_pass:
        failers.append(fail_desc("A", a_model, a))
    if not b_pass:
        failers.append(fail_desc("B", b_model, b))

    if gate_rule == "both_passed":
        reason = "both critics cleared"
    elif gate_rule == "margin_override":
        ov_label = decision["override_label"]
        ov_model = a_model if ov_label == "A" else b_model
        reason = ("margin override: critic {}/{} overall {} >= margin {} ships "
                  "despite the other critic's veto ({})".format(
                      ov_label, ov_model, decision["override_overall"],
                      args.margin, ", ".join(failers)))
    else:
        reason = "failed: " + ", ".join(failers)

    verdict = {
        "verdict": "PASS" if passed else "SLOP",
        "gate_rule": gate_rule,
        "is_slop": a["is_slop"] or b["is_slop"],
        "threshold": args.threshold,
        "margin": args.margin,
        "overall_min": min(a["overall"], b["overall"]),
        "reason": reason,
        "critics": {
            "A": {"model": a_model, "passed": a_pass, **a},
            "B": {"model": b_model, "fell_back_from": b_fell_back_from, "passed": b_pass, **b},
        },
    }
    if gate_rule == "margin_override":
        # Audit trail: make it obvious to a human why a slop-flagged page shipped.
        verdict["margin_override"] = {
            "critic": decision["override_label"],
            "model": a_model if decision["override_label"] == "A" else b_model,
            "overall": decision["override_overall"],
            "margin": args.margin,
        }
    emit(verdict, 0 if passed else 1)


if __name__ == "__main__":
    main()

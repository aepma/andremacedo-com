#!/usr/bin/env python3
"""critic_discrimination.py — measure whether each craft critic actually DISCRIMINATES.

A two-critic gate only buys uncorrelated blind spots if BOTH critics move when the
pixels move. A critic that returns a near-flat vector on every input supplies no
signal and silently collapses the gate to a single critic. This harness measures
that property directly, against the two calibration fixtures in this directory.

It drives the SAME transport the production judge uses: it imports craft-judge.py
and reuses its SYSTEM prompt, its user-content builder (rubric + base64 image), its
JSON extractor and its normalizer. It additionally captures the RAW model text and
the token usage, so a flat vector can be attributed to the model, to the prompt, to
the transport, or to normalization — rather than guessed at.

Verdict (per critic), mirroring the build contract:
  fails to discriminate  iff  (good_overall - slop_overall) < MIN_SEPARATION
                          or  axis spread is zero on BOTH fixtures.

Fail-closed (TigerBeetle style): every precondition is asserted; a missing binary,
an unreadable fixture, an exhausted call budget or an unparseable response raises
or exits non-zero. Nothing degrades silently into a default score.

Budget: live model calls cost money. --budget-file persists the running count
ACROSS invocations so a measure/fix/re-measure cycle cannot overrun its cap.
"""
import argparse
import importlib.util
import json
import os
import statistics
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CJ_PATH = os.path.normpath(os.path.join(HERE, "..", "craft-judge.py"))
GOOD_HTML = os.path.join(HERE, "good.html")
SLOP_HTML = os.path.join(HERE, "slop.html")
SHOT_SH = os.path.normpath(os.path.join(HERE, "..", "screenshot-file.sh"))

MIN_SEPARATION = 1.0        # B3 threshold: below this, the critic does not discriminate
TARGET_SEPARATION = 1.5     # B5 target after a fix


def load_craft_judge():
    assert os.path.isfile(CJ_PATH), "craft-judge.py missing at {}".format(CJ_PATH)
    spec = importlib.util.spec_from_file_location("craft_judge", CJ_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for attr in ("SYSTEM", "build_user_content", "extract_json", "normalize",
                 "proxy_api_key", "AXES", "DEFAULT_RUBRIC"):
        assert hasattr(mod, attr), "craft-judge.py lost required symbol: {}".format(attr)
    return mod


class Budget:
    """Hard cap on live critic calls, persisted across invocations. Fail-closed."""

    def __init__(self, path, cap):
        assert cap > 0, "budget cap must be positive"
        self.path = path
        self.cap = cap
        self.used = 0
        if path and os.path.isfile(path):
            with open(path) as f:
                self.used = int(json.load(f)["used"])
        assert self.used <= cap, "budget file already over cap: {} > {}".format(self.used, cap)

    def spend(self, n=1):
        if self.used + n > self.cap:
            raise RuntimeError(
                "critic-call budget exhausted: {} used, cap {}, need {} more".format(
                    self.used, self.cap, n))
        self.used += n
        if self.path:
            with open(self.path, "w") as f:
                json.dump({"used": self.used, "cap": self.cap}, f)


def call_capture(cj, url, model, system, user_content, timeout):
    """One live critic call. Mirrors craft_judge.call_proxy's payload EXACTLY, but
    returns the raw text and usage so the response can be audited, not just scored."""
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user_content}],
        "temperature": 0.2,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = cj.proxy_api_key()
    assert key, "no LITELLM_MASTER_KEY available; refusing to call the proxy unauthenticated"
    headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=payload, headers=headers)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode("utf-8"))
    elapsed = round(time.time() - t0, 1)
    content = body["choices"][0]["message"]["content"]
    return {
        "raw": content,
        "usage": body.get("usage") or {},
        "elapsed_s": elapsed,
        "payload_bytes": len(payload),
    }


def axis_spread(axes, axis_names):
    vals = [axes[a] for a in axis_names]
    return round(max(vals) - min(vals), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--critic-a", required=True)
    ap.add_argument("--critic-b", required=True)
    ap.add_argument("--good", default="/tmp/craft-fixture-good.jpg")
    ap.add_argument("--slop", default="/tmp/craft-fixture-slop.jpg")
    ap.add_argument("--good-mobile", help="optional mobile render for the good fixture,\n                                          matching what the production judge sends")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--url", default="http://localhost:4000/v1/chat/completions")
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--rubric")
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget-cap", type=int, default=24)
    ap.add_argument("--budget-file", default="/tmp/craft-critic-call-budget.json")
    ap.add_argument("--label", default="")
    ap.add_argument("--only", choices=["A", "B"],
                    help="run only this critic (lets a long measurement be taken in\n                          foreground chunks without leaving a background process)")
    args = ap.parse_args()

    cj = load_craft_judge()
    rubric_path = args.rubric or cj.DEFAULT_RUBRIC
    assert os.path.isfile(rubric_path), "rubric missing: {}".format(rubric_path)
    for p in (args.good, args.slop):
        assert os.path.isfile(p), "fixture render missing: {}".format(p)
        assert os.path.getsize(p) > 0, "fixture render is EMPTY: {}".format(p)

    rubric = open(rubric_path, encoding="utf-8").read()
    fixtures = {"good": args.good, "slop": args.slop}
    critics = {"A": args.critic_a, "B": args.critic_b}
    if args.only:
        critics = {args.only: critics[args.only]}
    budget = Budget(args.budget_file, args.budget_cap)

    results = {"label": args.label, "rubric_path": rubric_path,
               "rubric_sha_len": len(rubric), "critics": critics,
               "fixtures": {k: {"path": v, "bytes": os.path.getsize(v)} for k, v in fixtures.items()},
               "runs": []}

    for label, model in critics.items():
        for fx, path in fixtures.items():
            mobile = args.good_mobile if fx == "good" else None
            content = cj.build_user_content(rubric, path, mobile)
            n_images = sum(1 for p in content if p.get("type") == "image_url")
            expect = 2 if mobile and os.path.isfile(mobile) else 1
            assert n_images == expect, "expected {} image part(s), built {}".format(expect, n_images)
            for i in range(1, args.runs + 1):
                budget.spend(1)
                try:
                    cap = call_capture(cj, args.url, model, cj.SYSTEM, content, args.timeout)
                except Exception as e:  # fail-closed: a call we cannot score is not a zero
                    print("CALL FAILED critic={} fixture={} run={}: {}".format(label, fx, i, e),
                          file=sys.stderr)
                    results["runs"].append({"critic": label, "model": model, "fixture": fx,
                                            "run": i, "error": repr(e)})
                    continue
                parsed = cj.extract_json(cap["raw"])
                norm = cj.normalize(parsed)
                results["runs"].append({
                    "critic": label, "model": model, "fixture": fx, "run": i,
                    "budget_used_after": budget.used,
                    "elapsed_s": cap["elapsed_s"], "usage": cap["usage"],
                    "payload_bytes": cap["payload_bytes"],
                    "raw_axes_keys": sorted((parsed.get("axes") or {}).keys()),
                    "raw_axes": parsed.get("axes"),
                    "raw_overall": parsed.get("overall"),
                    "axes": norm["axes"], "overall": norm["overall"],
                    "is_slop": norm["is_slop"],
                    "axis_spread": axis_spread(norm["axes"], cj.AXES),
                    "findings": norm["findings"], "what_works": norm["what_works"],
                    "reasoning": norm["reasoning"],
                    "raw_len": len(cap["raw"]),
                })
                r = results["runs"][-1]
                print("{} {}/{} run{} overall={} spread={} slop={} axes={}".format(
                    label, model, fx, i, r["overall"], r["axis_spread"], r["is_slop"],
                    json.dumps(r["axes"])), flush=True)

    # ---- verdicts -------------------------------------------------------
    verdicts = {}
    for label, model in critics.items():
        per = {}
        for fx in fixtures:
            rs = [r for r in results["runs"]
                  if r["critic"] == label and r["fixture"] == fx and "overall" in r]
            if not rs:
                per[fx] = None
                continue
            per[fx] = {
                "n": len(rs),
                "overalls": [r["overall"] for r in rs],
                "mean_overall": round(statistics.fmean(r["overall"] for r in rs), 3),
                "axis_spreads": [r["axis_spread"] for r in rs],
                "max_axis_spread": max(r["axis_spread"] for r in rs),
                "is_slop": [r["is_slop"] for r in rs],
            }
        ok = per.get("good") and per.get("slop")
        if not ok:
            verdicts[label] = {"model": model, "discriminates": False,
                               "reason": "a fixture produced no scoreable run"}
            continue
        sep = round(per["good"]["mean_overall"] - per["slop"]["mean_overall"], 3)
        spread_zero_both = (per["good"]["max_axis_spread"] == 0
                            and per["slop"]["max_axis_spread"] == 0)
        fails = (sep < MIN_SEPARATION) or spread_zero_both
        verdicts[label] = {
            "model": model,
            "good_mean_overall": per["good"]["mean_overall"],
            "slop_mean_overall": per["slop"]["mean_overall"],
            "separation": sep,
            "max_axis_spread_good": per["good"]["max_axis_spread"],
            "max_axis_spread_slop": per["slop"]["max_axis_spread"],
            "discriminates": not fails,
            "meets_target_1_5": sep >= TARGET_SEPARATION,
            "per_fixture": per,
        }
    results["verdicts"] = verdicts
    results["budget_used_total"] = budget.used
    results["budget_cap"] = budget.cap

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n--- VERDICTS ---")
    for label, v in verdicts.items():
        print("critic {} ({}): separation={} spread_good={} spread_slop={} -> {}".format(
            label, v["model"], v.get("separation"), v.get("max_axis_spread_good"),
            v.get("max_axis_spread_slop"),
            "DISCRIMINATES" if v["discriminates"] else "FAILS TO DISCRIMINATE"))
    print("critic calls used: {}/{}".format(budget.used, budget.cap))
    failed_calls = [r for r in results["runs"] if "error" in r]
    if failed_calls:
        print("{} call(s) failed".format(len(failed_calls)), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

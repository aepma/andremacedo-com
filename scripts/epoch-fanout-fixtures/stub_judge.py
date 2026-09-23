#!/usr/bin/env python3
"""Stub craft judge for test_orchestration.py: no model call.

Honours craft-judge.py's CLI and output contract for the --tone path. Scores are
canned per candidate (read from the cand<N> directory in --desktop) so that the
candidate with the single highest critic score is NOT the min-of-critics winner:
  cand1: A combined 9.5, B combined 7.0  -> min 7.0
  cand3: A combined 8.0, B combined 7.8  -> min 7.8   (expected winner)
  cand4: A combined 7.6, B combined 7.5  -> min 7.5
A slot listed in STUB_JUDGE_ERROR returns exit 2 (critic unobtainable).
"""
import argparse, json, os, re, sys

ap = argparse.ArgumentParser()
ap.add_argument("--desktop"); ap.add_argument("--mobile"); ap.add_argument("--margin")
ap.add_argument("--wall-budget"); ap.add_argument("--json-out"); ap.add_argument("--quiet", action="store_true")
ap.add_argument("--tone", action="store_true"); ap.add_argument("--print-wall-budget", action="store_true")
a = ap.parse_args()
if a.print_wall_budget:
    print(5)
    sys.exit(0)
assert a.tone, "fan-out must request the tone axis"
slot = re.search(r"cand(\d+)", a.desktop).group(1)
if slot in os.environ.get("STUB_JUDGE_ERROR", "").split(","):
    json.dump({"verdict": "ERROR", "is_slop": True, "error": "critic B unobtainable: stub"},
              open(a.json_out, "w"))
    sys.exit(2)
table = {"1": (9.5, 7.0), "2": (9.9, 9.9), "3": (8.0, 7.8), "4": (7.6, 7.5)}
ca, cb = table[slot]


def critic(model, comb):
    # overall and tone both equal to comb, so combined == comb exactly.
    axes = {k: 8.0 for k in ("type_scale", "spacing_system", "focal_hierarchy", "restraint",
                             "hero", "composition", "type_craft", "color", "stranger_test")}
    axes["tone"] = comb
    return {"model": model, "passed": True, "axes": axes, "overall": comb, "is_slop": False,
            "findings": [], "what_works": [], "reasoning": "stub", "combined": comb}


v = {"verdict": "PASS", "gate_rule": "both_passed", "is_slop": False, "reason": "both critics cleared",
     "critics": {"A": critic("stub-opus", ca), "B": critic("stub-grok", cb)},
     "tone_axis": True, "combined_min": min(ca, cb)}
json.dump(v, open(a.json_out, "w"))
sys.exit(0)

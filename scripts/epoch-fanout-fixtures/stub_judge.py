#!/usr/bin/env python3
"""Stub craft judge for test_orchestration.py: no model call.

Honours craft-judge.py's CLI and output contract. Every candidate passes with
canned overall scores, except a slot listed in STUB_JUDGE_SLOP (verdict SLOP,
exit 1: the craft gate fails it) or STUB_JUDGE_ERROR (exit 2: a critic was
unobtainable). The fan-out must not ask for the tone axis any more.
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
assert not a.tone, "the fan-out no longer ranks on the tone axis"
slot = re.search(r"cand(\d+)", a.desktop).group(1)
if slot in os.environ.get("STUB_JUDGE_ERROR", "").split(","):
    json.dump({"verdict": "ERROR", "is_slop": True, "error": "critic B unobtainable: stub"},
              open(a.json_out, "w"))
    sys.exit(2)
slop = slot in os.environ.get("STUB_JUDGE_SLOP", "").split(",")


def critic(model, overall):
    axes = {k: overall for k in ("type_scale", "spacing_system", "focal_hierarchy", "restraint",
                                 "hero", "composition", "type_craft", "color", "stranger_test")}
    return {"model": model, "passed": not slop, "axes": axes, "overall": overall, "is_slop": slop,
            "findings": [], "what_works": [], "reasoning": "stub"}


v = {"verdict": "SLOP" if slop else "PASS", "gate_rule": "failed" if slop else "both_passed",
     "is_slop": slop, "reason": "stub", "critics": {"A": critic("stub-opus", 8.0 if not slop else 5.0),
                                                   "B": critic("stub-grok", 7.6 if not slop else 5.0)}}
json.dump(v, open(a.json_out, "w"))
sys.exit(1 if slop else 0)

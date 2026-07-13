#!/usr/bin/env python3
"""Fixture test for the craft-judge margin gate rule (decide_gate).

Feeds synthetic critic verdicts through the pure gate decision and asserts the
ship/fail outcome and which rule fired. Fail-closed: exit 1 if ANY case fails
(the caller must NOT commit on a non-zero exit).

Cases (mirrors the approved proposal):
  1. A 7.8 clean, B slop            -> PASS via margin_override (the gen-230 shape)
  2. A slop, B slop                 -> FAIL (both slop)
  3. A 7.1 clean, B slop            -> FAIL (lone pass below the 7.3 margin)
  4. A 8.0 clean, B 7.5 clean       -> PASS via both_passed
  5. A ERROR/unobtainable, B 9.0    -> FAIL (ERROR fail-closed, never overridden)
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CJ_PATH = os.path.join(HERE, "..", "craft-judge.py")
spec = importlib.util.spec_from_file_location("craft_judge", CJ_PATH)
cj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cj)

THRESHOLD = 7.0
MARGIN = 7.3


def v(overall, is_slop):
    """A minimal normalized critic verdict as decide_gate consumes it."""
    return {"overall": overall, "is_slop": is_slop,
            "axes": {}, "findings": [], "what_works": [], "reasoning": ""}


ERROR = None  # a critic that could not be obtained

CASES = [
    ("1 gen-230 shape: A 7.8 clean, B slop", v(7.8, False), v(0.0, True), True,  "margin_override"),
    ("2 both slop",                          v(0.0, True),  v(0.0, True), False, "failed"),
    ("3 lone pass A 7.1 below margin, B slop", v(7.1, False), v(0.0, True), False, "failed"),
    ("4 both pass: A 8.0, B 7.5",            v(8.0, False), v(7.5, False), True,  "both_passed"),
    ("5 A ERROR unobtainable, B 9.0 clean",  ERROR,         v(9.0, False), False, "failed"),
]


def main():
    fails = []
    for name, a, b, exp_ship, exp_rule in CASES:
        d = cj.decide_gate(a, b, THRESHOLD, MARGIN)
        got_ship, got_rule = d["passed"], d["gate_rule"]
        ok = (got_ship == exp_ship) and (got_rule == exp_rule)
        print("[{}] {}\n      expected: ship={} rule={} | actual: ship={} rule={}".format(
            "PASS" if ok else "FAIL", name, exp_ship, exp_rule, got_ship, got_rule))
        if not ok:
            fails.append((name, exp_ship, exp_rule, got_ship, got_rule))

    if fails:
        print("\n{} case(s) FAILED — do NOT commit.".format(len(fails)))
        return 1
    print("\nAll 5 gate cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
  6. both clean 9.0, A stranger 6.9 -> FAIL via stranger_floor (rubric v2 floor)
  7. A 9.0 clean, B slop w/o axis   -> FAIL via stranger_floor (missing axis = 0)
  8. both clean, both stranger 7.0  -> PASS via both_passed (floor is >= 7)
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


def v(overall, is_slop, stranger=9.0):
    """A minimal normalized critic verdict as decide_gate consumes it.

    stranger_test defaults to a clearing score so the five original cases keep
    their original verdicts; the floor cases below set it explicitly."""
    return {"overall": overall, "is_slop": is_slop,
            "axes": {"stranger_test": stranger}, "findings": [], "what_works": [],
            "reasoning": ""}


ERROR = None  # a critic that could not be obtained

CASES = [
    ("1 gen-230 shape: A 7.8 clean, B slop", v(7.8, False), v(0.0, True), True,  "margin_override"),
    ("2 both slop",                          v(0.0, True),  v(0.0, True), False, "failed"),
    ("3 lone pass A 7.1 below margin, B slop", v(7.1, False), v(0.0, True), False, "failed"),
    ("4 both pass: A 8.0, B 7.5",            v(8.0, False), v(7.5, False), True,  "both_passed"),
    ("5 A ERROR unobtainable, B 9.0 clean",  ERROR,         v(9.0, False), False, "failed"),
    # rubric_version 2: the stranger_test floor (visitor floor, 2026-09-06)
    ("6 both 9.0 clean, A stranger_test 6.9", v(9.0, False, 6.9), v(9.0, False), False, "stranger_floor"),
    ("7 A 9.0 clean, B slop, B lacks the axis", v(9.0, False), v(0.0, True, 0.0), False, "stranger_floor"),
    ("8 both clean, both stranger_test 7.0",  v(8.0, False, 7.0), v(7.5, False, 7.0), True, "both_passed"),
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
    print("\nAll {} gate cases passed.".format(len(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

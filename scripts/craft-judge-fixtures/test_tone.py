#!/usr/bin/env python3
"""Fixture test for the optional tone axis (craft-judge.py --tone).

The tone axis ranks candidate epoch openings (epoch_fanout.py). It must never
change the craft gate: not the default prompt, not the craft overall, not the
gate rule. Offline; never calls the proxy. Exit 1 if ANY case fails.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("craft_judge", os.path.join(HERE, "..", "craft-judge.py"))
cj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cj)

RESULTS = []


def check(name, cond):
    RESULTS.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name)


craft = {a: 8.0 for a in cj.AXES}
raw = {"axes": dict(craft, tone=6.0), "overall": 8.0, "is_slop": False}

v_plain = cj.normalize(raw)
check("default normalize ignores tone", cj.TONE_AXIS not in v_plain["axes"])
v_tone = cj.normalize(raw, tone=True)
check("--tone normalize records tone", v_tone["axes"][cj.TONE_AXIS] == 6.0)
check("tone never enters overall", v_tone["overall"] == v_plain["overall"] == 8.0)
no_overall = cj.normalize({"axes": dict(craft, tone=0.0), "is_slop": False}, tone=True)
check("derived overall averages the 9 craft axes only", no_overall["overall"] == 8.0)
missing = cj.normalize({"axes": craft, "overall": 8.0, "is_slop": False}, tone=True)
check("missing tone normalizes to 0 (fail-closed)", missing["axes"][cj.TONE_AXIS] == 0.0)
check("combined = mean(overall, tone)", cj.combined_score(v_tone) == 7.0)
try:
    cj.combined_score(v_plain)
    check("combined asserts a --tone verdict", False)
except AssertionError:
    check("combined asserts a --tone verdict", True)
check("gate rule unchanged by tone",
      cj.decide_gate(v_tone, v_tone, 7.0, 7.3) == cj.decide_gate(v_plain, v_plain, 7.0, 7.3))

desk = os.path.join(HERE, "good.html")   # any existing file stands in for an image path
plain = cj.build_user_content("RUBRIC", desk, None)[0]["text"]
toned = cj.build_user_content("RUBRIC", desk, None, "TONE RUBRIC BODY")[0]["text"]
check("default prompt carries no tone section", "TONE RUBRIC" not in plain)
check("--tone prompt carries the tone rubric", "TONE RUBRIC BODY" in toned and "axes.tone" in toned)
rubric = open(cj.DEFAULT_TONE_RUBRIC, encoding="utf-8").read()
check("tone rubric quotes Andre's line verbatim",
      "I have no idea what I just saw but I can't stop thinking about it." in rubric)
args = cj.build_parser().parse_args(["--desktop", desk])
check("--tone is off by default", args.tone is False)

failed = [n for n, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
sys.exit(1 if failed else 0)

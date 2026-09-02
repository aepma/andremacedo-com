#!/usr/bin/env python3
"""Fixture test for the craft LEDGER and the gate's time budget.

Companion to test_gate.py, which covers the margin rule. This one covers the two
defects fixed on 2026-09-02:

  1. judge_verdict came from the SCORES, so a run killed at the wrapper's bound
     (exit 124) was written into state/craft-history.jsonl as a passing 8.0 —
     at the most recent point in the only craft series this system keeps.
  2. the wrapper bounded the judge at 240s while the per-critic budgets could
     spend 660s, so a run both critics had already cleared was killed anyway.

Fail-closed: exit 1 if ANY case fails. The caller must NOT commit on non-zero.
"""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
REPO = os.path.dirname(SCRIPTS)


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cj = load("craft_judge", "craft-judge.py")
er = load("epoch_review", "epoch_review.py")

CLEAN_JSON = {
    "verdict": "PASS", "gate_rule": "both_passed", "is_slop": False,
    "reason": "both critics cleared",
    "critics": {"A": {"overall": 8.0, "is_slop": False},
                "B": {"overall": 8.0, "is_slop": False}},
}
SLOP_JSON = {
    "verdict": "SLOP", "gate_rule": "failed", "is_slop": True,
    "reason": "failed: A(6.2<7.0), B(slop)",
    "critics": {"A": {"overall": 6.2, "is_slop": False},
                "B": {"overall": 5.5, "is_slop": True}},
}

CHECKS = []


def check(name):
    def register(fn):
        CHECKS.append((name, fn))
        return fn
    return register


def write_json(tmp, obj, filename="craft.json"):
    path = os.path.join(tmp, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return path


# ── defect 1: the verdict comes from the exit code, never from the scores ──
@check("judge_outcome maps every exit code the judge can produce")
def _():
    assert er.judge_outcome(0) == ("PASS", True), er.judge_outcome(0)
    assert er.judge_outcome(1) == ("SLOP", True)
    assert er.judge_outcome(2) == ("ERROR", True)
    assert er.judge_outcome("0") == ("PASS", True), "runner passes it as a string"
    assert er.judge_outcome(124) == ("TIMEOUT", False)
    assert er.judge_outcome("124") == ("TIMEOUT", False)
    assert er.judge_outcome(143) == ("TIMEOUT", False), "SIGTERM"
    assert er.judge_outcome(137) == ("TIMEOUT", False), "SIGKILL"
    assert er.judge_outcome(3) == ("CRASHED", False)
    assert er.judge_outcome(None) == ("UNKNOWN", False), "no exit code is not a pass"
    assert er.judge_outcome("") == ("UNKNOWN", False)
    assert er.judge_outcome("garbage") == ("UNKNOWN", False)


@check("a killed run with two clearing critics is NOT recorded as a pass")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        entry = er.craft_entry_from_judge(write_json(tmp, CLEAN_JSON), 240, "124")
    assert entry["judge_verdict"] == "TIMEOUT", entry
    assert not er.verdict_is_pass(entry["judge_verdict"])
    assert entry["status"] == "unobtainable", entry
    assert entry["min_overall"] is None, "a killed run's JSON is a previous run's"
    assert entry["critic_a"] is None and entry["critic_b"] is None
    assert not er.is_scored(entry)


@check("a completed passing run is still scored, with a PASS")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        entry = er.craft_entry_from_judge(write_json(tmp, CLEAN_JSON), 241, "0")
    assert entry["judge_verdict"] == "PASS", entry
    assert entry["status"] == "scored" and entry["min_overall"] == 8.0, entry
    assert er.is_scored(entry)


@check("a genuine slop run keeps its real scores in the series")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        entry = er.craft_entry_from_judge(write_json(tmp, SLOP_JSON), 242, "1")
    # A failing gate is a COMPLETED measurement. Demoting it would hide a
    # declining epoch from the plateau detector, which is the opposite defect.
    assert entry["judge_verdict"] == "SLOP", entry
    assert entry["status"] == "scored" and entry["min_overall"] == 5.5, entry


@check("a judge self-report that disagrees with the exit code never wins")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        # JSON says PASS, exit says slop: the exit code decides, the JSON's claim
        # is kept only as an audit field.
        entry = er.craft_entry_from_judge(write_json(tmp, CLEAN_JSON), 243, "1")
    assert entry["judge_verdict"] == "SLOP", entry
    assert entry.get("judge_json_verdict") == "PASS", entry
    assert entry.get("verdict_mismatch") is True, entry


# ── defect 1: corrections are append-only and honoured by every reader ──
@check("apply_corrections folds a correction and is idempotent")
def _():
    history = [
        {"gen": 239, "timestamp": "t1", "min_overall": 8.0, "status": "scored",
         "judge_verdict": "PASS"},
        {"gen": 240, "timestamp": "t2", "min_overall": 8.0, "status": "scored",
         "judge_verdict": "PASS", "judge_exit": "124"},
        {"record": "correction", "gen": 240, "timestamp": "t3", "corrects": "t2",
         "status": "unobtainable", "min_overall": None, "judge_verdict": "TIMEOUT",
         "note": "killed at the wrapper bound; no measurement exists"},
    ]
    once = er.apply_corrections(history)
    assert len(once) == 2, "the correction row is consumed, not emitted"
    fixed = [e for e in once if e["gen"] == 240][0]
    assert fixed["status"] == "unobtainable" and fixed["min_overall"] is None, fixed
    assert fixed["judge_verdict"] == "TIMEOUT"
    assert fixed["corrected_by"] == ["t3"]
    assert fixed["correction_note"].startswith("killed at")
    assert er.apply_corrections(once) == once, "must be idempotent"
    assert [e["gen"] for e in er.scored_entries(history)] == [239]
    assert history[1]["status"] == "scored", "the input list is never mutated"


@check("a correction naming a different timestamp does not touch the row")
def _():
    history = [
        {"gen": 240, "timestamp": "t2", "min_overall": 8.0, "status": "scored"},
        {"record": "correction", "gen": 240, "timestamp": "t3", "corrects": "OTHER",
         "status": "unobtainable", "min_overall": None},
    ]
    fixed = er.apply_corrections(history)
    assert fixed[0]["status"] == "scored", fixed


@check("the live series no longer reads generation 240 as a passing 8.0")
def _():
    path = os.path.join(REPO, "state", "craft-history.jsonl")
    if not os.path.isfile(path):
        raise AssertionError(f"craft history missing at {path}")
    raw = er.load_jsonl(path)
    assert any(e.get("gen") == 240 and e.get("min_overall") == 8.0
               and e.get("judge_verdict") == "PASS" for e in raw), \
        "the original gen-240 line must still be on disk: the series is append-only"
    for e in er.scored_entries(raw):
        assert e.get("gen") != 240, f"gen 240 still reads as scored: {e}"


# ── defect 2: the wrapper bound and the critic budgets are reconciled ──
@check("the wall budget covers every critic path including retry and fallback")
def _():
    for timeout_a, timeout_b, retries in ((120.0, 90.0, 2), (120.0, 90.0, 1),
                                          (60.0, 300.0, 3), (5.0, 5.0, 1)):
        budget = cj.wall_budget_seconds(timeout_a, timeout_b, retries)
        assert budget >= retries * timeout_a, (timeout_a, timeout_b, retries, budget)
        assert budget >= retries * timeout_b + retries * timeout_a, \
            "critic B's fallback runs at critic A's budget and must fit"
        assert budget > max(retries * timeout_a,
                            retries * timeout_b + retries * timeout_a), \
            "the budget must leave room for encoding and network overhead"


@check("the judge's shipped defaults fit inside the budget it publishes")
def _():
    # Read the defaults at runtime rather than restating them, so this cannot
    # pass against numbers the judge no longer runs on.
    ta, tb, r = cj.TIMEOUT_A_DEFAULT, cj.TIMEOUT_B_DEFAULT, cj.RETRIES_DEFAULT
    budget = cj.wall_budget_seconds(ta, tb, r)
    # Both critics answering inside their OWN budgets is the case that must never
    # be killed. Concurrently that is max(ta, tb) plus overhead.
    assert budget > max(ta, tb) + cj.CRITIC_OVERHEAD_SECONDS, budget
    assert budget >= r * tb + r * ta, "the fallback path must fit too"


@check("wall_budget_seconds rejects nonsense rather than returning one")
def _():
    for bad in ((0, 90, 2), (120, -1, 2), (120, 90, 0)):
        try:
            cj.wall_budget_seconds(*bad)
        except AssertionError:
            continue
        raise AssertionError(f"accepted {bad} instead of failing closed")


def main():
    failed = []
    for name, fn in CHECKS:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — a failed check is the output
            failed.append((name, exc))
            print(f"[FAIL] {name}\n       {type(exc).__name__}: {exc}")
        else:
            print(f"[PASS] {name}")
    if failed:
        print(f"\n{len(failed)} case(s) FAILED — do NOT commit.")
        return 1
    print(f"\nAll {len(CHECKS)} ledger/budget cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

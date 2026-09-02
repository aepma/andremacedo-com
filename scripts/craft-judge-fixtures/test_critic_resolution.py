#!/usr/bin/env python3
"""Fixture test for runtime critic-model resolution (resolve_critic).

Why this exists: on 2026-09-02 the craft gate could not pass on craft grounds at
all. Critic B was pinned to grok-4-1-fast-reasoning, an id the proxy had retired
(HTTP 400 "Invalid model name"). The judge's fallback caught that exception and
substituted gemini-3.5-flash on every run, silently — the verdict still named the
configured critic, and the known-good fixture scored 6.0 against a 7.0 threshold.
A pinned model id is a version string, and version strings die under this file.

Fail-closed: exit 1 if ANY case fails. Runs entirely offline against synthetic
model lists; it never calls the proxy.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "craft_judge", os.path.join(HERE, "..", "craft-judge.py"))
cj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cj)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print("[{}] {}{}".format("PASS" if ok else "FAIL", name,
                             "\n      " + detail if detail and not ok else ""))


def main():
    # The live proxy list as measured 2026-09-02: the retired grok id is absent.
    LIVE = {"claude-opus-4-8-oauth", "claude-opus-5-oauth", "gemini-3.5-flash",
            "gemini-3.6-flash", "grok-4.20-fast", "grok-4.5", "grok-4.3", "grok-4.6"}

    got = cj.resolve_critic(cj.CRITIC_B_CANDIDATES, LIVE)
    check("critic B resolves to a live grok, not the retired id",
          got in LIVE and "grok" in got, f"resolved {got!r}")

    check("the retired id is no longer a candidate",
          "grok-4-1-fast-reasoning" not in cj.CRITIC_B_CANDIDATES,
          f"candidates: {cj.CRITIC_B_CANDIDATES}")

    # A dead head of the list is skipped rather than returned.
    got = cj.resolve_critic(("dead-model-1", "dead-model-2", "grok-4.5"), LIVE)
    check("a dead candidate is skipped for the next live one",
          got == "grok-4.5", f"resolved {got!r}")

    # An explicit --critic-b that IS live wins over the default order.
    got = cj.resolve_critic(cj.CRITIC_B_CANDIDATES, LIVE, requested="grok-4.3")
    check("an explicit live request wins over the default order",
          got == "grok-4.3", f"resolved {got!r}")

    # An explicit --critic-b that is DEAD does not become a silent substitution:
    # it is tried first, found absent, and the declared order decides.
    got = cj.resolve_critic(cj.CRITIC_B_CANDIDATES, LIVE, requested="grok-4-1-fast-reasoning")
    check("an explicit dead request falls through to a live candidate",
          got == cj.CRITIC_B_CANDIDATES[0], f"resolved {got!r}")

    # Nothing live -> None, so the caller can fail closed and say what it wanted.
    got = cj.resolve_critic(cj.CRITIC_B_CANDIDATES, {"gemini-3.5-flash"})
    check("no live candidate resolves to None rather than a guess",
          got is None, f"resolved {got!r}")

    # ... and in exactly that case the fallback family is what carries the run.
    got = cj.resolve_critic(cj.CRITIC_B_FALLBACK_CANDIDATES, {"gemini-3.5-flash"})
    check("the fallback family still resolves when no grok is live",
          got == "gemini-3.5-flash", f"resolved {got!r}")

    # An empty candidate list is a wiring defect, not a None.
    try:
        cj.resolve_critic((), LIVE)
        check("an empty candidate list raises rather than returning None", False,
              "returned instead of raising")
    except AssertionError:
        check("an empty candidate list raises rather than returning None", True)

    # The two critics must never be able to resolve to the same model: two
    # critics from one model is one critic with extra steps, and the whole design
    # is uncorrelated blind spots.
    overlap = set(cj.CRITIC_A_CANDIDATES) & set(cj.CRITIC_B_CANDIDATES)
    check("critic A and critic B declare disjoint models",
          not overlap, f"overlap: {overlap}")
    overlap = set(cj.CRITIC_A_CANDIDATES) & set(cj.CRITIC_B_FALLBACK_CANDIDATES)
    check("critic A and critic B's fallback declare disjoint models",
          not overlap, f"overlap: {overlap}")

    # The deprecated gemini must not be reachable as a fallback.
    check("gemini-2.5-pro is not reachable as a critic",
          "gemini-2.5-pro" not in (tuple(cj.CRITIC_A_CANDIDATES)
                                   + tuple(cj.CRITIC_B_CANDIDATES)
                                   + tuple(cj.CRITIC_B_FALLBACK_CANDIDATES)))

    # The argparse defaults must stay the head of their own lists, or --critic-b
    # with no value would name a model the resolver does not prefer.
    check("the argparse defaults are the head of their candidate lists",
          (cj.CRITIC_A == cj.CRITIC_A_CANDIDATES[0]
           and cj.CRITIC_B == cj.CRITIC_B_CANDIDATES[0]
           and cj.CRITIC_B_FALLBACK == cj.CRITIC_B_FALLBACK_CANDIDATES[0]))

    fails = [r for r in RESULTS if not r[1]]
    if fails:
        print("\n{} case(s) FAILED — do NOT commit.".format(len(fails)))
        return 1
    print("\nAll {} critic-resolution cases passed.".format(len(RESULTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

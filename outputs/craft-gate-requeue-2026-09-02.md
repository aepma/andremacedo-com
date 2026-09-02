# craft-gate fix — requeue run, assertion evidence

Requeue of the craft-gate build (defect 1: the ledger recorded a killed run as a
pass; defect 2: the wrapper bound was smaller than the sum of the critic
budgets). The first attempt landed commit `f3ea7bd` in this repository but was
recorded upstream as having committed nothing, so the work was requeued.

This file is this run's evidence: every assertion re-run against live state, in
order, with the exact command, the observed output, and the exit code read
immediately after the command. Where an assertion is satisfied by work the first
attempt already committed, it is re-run here rather than inherited.

Prior attempt's own write-up: `outputs/craft-gate-fix-2026-09-02.md`.

---

## Starting state

    cd ~/andremacedo.com-engine-c && git log --oneline -2

    f3ea7bd craft-gate: derive the craft verdict from the judge's exit code, and reconcile the wrapper bound with the critic budgets
    f1c5528 daily-deploy: record the cause when the daily publish fails

exit 0

Working tree carried unrelated in-flight work from other lanes at start
(`data/external.json` modified; `outputs/craft-critic-discrimination-2026-09-02.md`,
`outputs/daily-deploy-diagnosis-2026-09-02.md` and
`scripts/craft-judge-fixtures/critic_discrimination.py` untracked). None of it is
mine and none of it is committed by this run.

---

## A1 — baseline: the existing gate unit test, before any change by this run

Command:

    cd ~/andremacedo.com-engine-c && python3 scripts/craft-judge-fixtures/test_gate.py; echo "EXIT=$?"

Output:

    [PASS] 1 gen-230 shape: A 7.8 clean, B slop
          expected: ship=True rule=margin_override | actual: ship=True rule=margin_override
    [PASS] 2 both slop
          expected: ship=False rule=failed | actual: ship=False rule=failed
    [PASS] 3 lone pass A 7.1 below margin, B slop
          expected: ship=False rule=failed | actual: ship=False rule=failed
    [PASS] 4 both pass: A 8.0, B 7.5
          expected: ship=True rule=both_passed | actual: ship=True rule=both_passed
    [PASS] 5 A ERROR unobtainable, B 9.0 clean
          expected: ship=False rule=failed | actual: ship=False rule=failed

    All 5 gate cases passed.

**exit 0.** It does not error on collection. The margin gate is untouched by this
build and still decides exactly as it did.

The ledger/budget suite the first attempt added was run alongside it, same
conditions:

    cd ~/andremacedo.com-engine-c && python3 scripts/craft-judge-fixtures/test_ledger.py; echo "EXIT=$?"

    [PASS] judge_outcome maps every exit code the judge can produce
    [PASS] a killed run with two clearing critics is NOT recorded as a pass
    [PASS] a completed passing run is still scored, with a PASS
    [PASS] a genuine slop run keeps its real scores in the series
    [PASS] a judge self-report that disagrees with the exit code never wins
    [PASS] apply_corrections folds a correction and is idempotent
    [PASS] a correction naming a different timestamp does not touch the row
    [PASS] the live series no longer reads generation 240 as a passing 8.0
    [PASS] the wall budget covers every critic path including retry and fallback
    [PASS] the judge's shipped defaults fit inside the budget it publishes
    [PASS] wall_budget_seconds rejects nonsense rather than returning one

    All 11 ledger/budget cases passed.

**exit 0.**

---

## A2 — append-craft with two clearing critics and judge-exit 124

Throwaway copy of the real series, plus a synthetic craft JSON carrying two
critics at 8.0 and a self-reported PASS — the exact shape that produced the bad
row for generation 240:

    cd ~/andremacedo.com-engine-c && rm -rf /tmp/a2 && mkdir -p /tmp/a2 \
      && cp state/craft-history.jsonl /tmp/a2/history.jsonl && cat > /tmp/a2/craft.json <<'EOF'
    {"verdict": "PASS", "passed": true, "gate_rule": "both_passed",
     "critics": {"A": {"overall": 8.0, "is_slop": false},
                 "B": {"overall": 8.0, "is_slop": false}}}
    EOF

Drive:

    cd ~/andremacedo.com-engine-c && python3 scripts/epoch_review.py append-craft \
      --history /tmp/a2/history.jsonl --craft-json /tmp/a2/craft.json \
      --gen 999 --judge-exit 124; echo "EXIT=$?"

**exit 0.** The appended line, in full:

    {"gen": 999, "timestamp": "2026-09-02T12:56:24Z", "critic_a": null, "critic_b": null, "min_overall": null, "status": "unobtainable", "judge_exit": "124", "judge_verdict": "TIMEOUT", "note": "judge did not complete (exit '124'); no verdict and no scores recorded — any JSON at the output path belongs to an earlier run"}

Expected: the appended record does not carry a passing verdict. **Met.**
`judge_verdict` is `TIMEOUT`, `status` is `unobtainable`, and the two 8.0s in the
JSON are not attributed to the generation at all: a judge that did not reach its
own `emit()` did not write that file, so its contents belong to an earlier run.
Both clearing critics and a self-reported `PASS` were present and neither moved
the verdict.

---

## A3 — the same append with judge-exit 0

    cd ~/andremacedo.com-engine-c && python3 scripts/epoch_review.py append-craft \
      --history /tmp/a2/history.jsonl --craft-json /tmp/a2/craft.json \
      --gen 998 --judge-exit 0; echo "EXIT=$?"

**exit 0.** The appended line, in full:

    {"gen": 998, "timestamp": "2026-09-02T12:56:29Z", "critic_a": 8.0, "critic_b": 8.0, "min_overall": 8.0, "status": "scored", "judge_exit": "0", "judge_verdict": "PASS"}

Expected: the appended record carries a passing verdict. **Met.** Same craft
JSON, same scores; only the exit code differs, and the exit code is the only
thing the verdict is derived from. The throwaway series went 15 -> 17 lines; the
real one was not touched by A2 or A3.

---

## A4 — the real series, before and after the correction

Line count before (the commit that carries the fix, at its parent):

    cd ~/andremacedo.com-engine-c && git show f3ea7bd^:state/craft-history.jsonl | wc -l
    14

exit 0

Line count now:

    cd ~/andremacedo.com-engine-c && wc -l < state/craft-history.jsonl
    15

exit 0

The count did not decrease, and the file's diff in that commit is a single
appended line with no deletion and no in-place edit: the series is still
append-only.

Every line mentioning generation 240:

    cd ~/andremacedo.com-engine-c && grep -n '"gen": 240' state/craft-history.jsonl

    14:{"gen": 240, "timestamp": "2026-08-31T04:38:31Z", "critic_a": 8.0, "critic_b": 8.0, "min_overall": 8.0, "status": "scored", "judge_exit": "124", "judge_verdict": "PASS"}
    15:{"record": "correction", "gen": 240, "timestamp": "2026-09-02T11:17:08Z", "corrects": "2026-08-31T04:38:31Z", "status": "unobtainable", "critic_a": null, "critic_b": null, "min_overall": null, "judge_verdict": "TIMEOUT", "note": "Judge killed by the runner wrapper at its 240s bound (exit 124); the generation was reverted and never deployed, and state/craft-judge-latest.json was last written by gen 239 (commit 5b04d79, 2026-08-20), so the 8.0/8.0 recorded here are gen 239's scores read from a file this run never wrote. No craft measurement exists for gen 240.", "judge_exit": "124"}

exit 0. The original bad row is still there, verbatim, with its provenance
intact. The correction sits after it.

What the epoch-health path actually reads, through the same functions the
consumers call:

    cd ~/andremacedo.com-engine-c && python3 - <<'PY'
    import importlib.util, json
    spec = importlib.util.spec_from_file_location("epoch_review", "scripts/epoch_review.py")
    er = importlib.util.module_from_spec(spec); spec.loader.exec_module(er)
    h = er.load_craft_history(er.craft_history_path("state"))
    print("rows after folding corrections:", len(h))
    for e in h:
        if e.get("gen") == 240:
            print("gen 240 as epoch health reads it:", json.dumps(e, ensure_ascii=False))
    print("gen 240 in scored_entries:", [e["gen"] for e in er.scored_entries(h) if e.get("gen")==240])
    print("last 3 scored gens:", [(e["gen"], e["min_overall"]) for e in er.scored_entries(h)][-3:])
    PY

    rows after folding corrections: 14
    gen 240 as epoch health reads it: {"gen": 240, "timestamp": "2026-08-31T04:38:31Z", "critic_a": null, "critic_b": null, "min_overall": null, "status": "unobtainable", "judge_exit": "124", "judge_verdict": "TIMEOUT", "correction_note": "Judge killed by the runner wrapper at its 240s bound (exit 124); ...", "corrected_by": ["2026-09-02T11:17:08Z"]}
    gen 240 in scored_entries: []
    last 3 scored gens: [(237, 7.0), (238, 7.6), (239, 8.0)]

exit 0

And the plateau detector, which is the consumer that decides whether an epoch has
died:

    cd ~/andremacedo.com-engine-c && python3 scripts/epoch_review.py plateau --history state/craft-history.jsonl

    "scored_available": 11, "excluded_unobtainable": 3,
    "series": [{"gen": 236, "min_overall": 7.5}, {"gen": 237, "min_overall": 7.0},
               {"gen": 238, "min_overall": 7.6}, {"gen": 239, "min_overall": 8.0}],
    "spread": 1.0, "flat": false, "verdict": "NOT_FLAT"

exit 0. Generation 240 is not in the series and contributes no 8.0 to it.
Expected: the count did not decrease, and generation 240 is no longer readable as
a passing 8.0 by the epoch-health path. **Met on both.**

The series does have programmatic readers, so the "nothing reads it" escape
hatch does not apply. Both go through the correcting loader:

    cd ~/andremacedo.com-engine-c && grep -rn 'load_craft_history' scripts/*.py

    scripts/build_prompt.py:601:    history = er.load_craft_history(er.craft_history_path(state_dir))
    scripts/record-generation.py:149:        history = er.load_craft_history(er.craft_history_path(state_dir))
    scripts/epoch_review.py:248:def load_craft_history(path):
    scripts/epoch_review.py:467:    history = load_craft_history(args.history)

exit 0. `build_prompt.py` renders the epoch-review section the agent reasons
against; `record-generation.py` runs the mechanical backstop that can end an
epoch. Those two plus the CLI are every reader of the series in the checkout.

---

## A5 — the wrapper bound and the per-critic budgets, read from the files

The wrapper no longer carries a bound of its own. `scripts/runner.sh`:

    CRAFT_WALL="$(python3 "$SCRIPT_DIR/craft-judge.py" --print-wall-budget 2>>"$ERROR_LOG")"
    CRAFT_WALL_EXIT=$?
    case "$CRAFT_WALL" in
      ''|*[!0-9]*) CRAFT_WALL_EXIT=1 ;;
    esac
    if [ "$CRAFT_WALL_EXIT" != "0" ] || [ "$CRAFT_WALL" -le 0 ]; then
      log_error "craft gate: could not read the judge's wall budget ... — fail-closed, no deploy"
      ...
    tmo "$CRAFT_WALL" python3 "$SCRIPT_DIR/craft-judge.py" \
      ... --wall-budget "$CRAFT_WALL" \
      --json-out "$CRAFT_RUN_OUT" --quiet 2>>"$ERROR_LOG"

The per-critic defaults, `scripts/craft-judge.py`:

    47:CRITIC_OVERHEAD_SECONDS = 30.0
    59:TIMEOUT_A_DEFAULT = 240.0
    60:TIMEOUT_B_DEFAULT = 90.0        # grok reasoning can be slower; beyond this -> fallback
    61:RETRIES_DEFAULT = 2             # attempts, not extra tries

exit 0 on both reads.

The bound as the runner reads it at runtime:

    cd ~/andremacedo.com-engine-c && python3 scripts/craft-judge.py --print-wall-budget

    stdout: 690
    stderr: critic A worst case 2x240.0s = 480.0s; critic B worst case 2x90.0s + fallback 2x240.0s = 660.0s; critics run concurrently so the pair costs max(480.0, 660.0) = 660.0s; + 30.0s overhead = 690s

exit 0

Worst-case arithmetic, including one retry and the fallback path: critic A is 2
attempts at 240s = 480s. Critic B is 2 attempts at 90s = 180s, and on failure the
fallback runs at critic A's budget for 2 more attempts = 480s, so the B path
worst case is 660s. The two critics run concurrently, so the pair costs the
slower path, 660s, plus 30s of overhead outside the per-request timeouts
(interpreter start, reading and base64-encoding two screenshots, proxy connect,
JSON parse, writing the output file) = **690s. The wrapper bound is 690s.**
Worst case is at or below the bound, with the critics concurrent. **Met.**

The relationship is enforced in code in both directions, not left as a comment:
the runner has no literal to drift and fails closed if it cannot read the number,
and the judge refuses to start — exit 2, before spending a critic call — if the
bound handed back is below its own worst case. Both numbers are derived from the
same `wall_budget_seconds()` over the live arguments, so editing either budget
moves the bound with it.

Fail-closed on a genuine timeout is preserved: any non-zero judge exit reverts
`index.html`, writes a `craft-fail` changelog line, notifies, and skips the
deploy. A killed run leaves the per-run output file empty and is reported as
"judge produced no verdict", not as a different generation's reason.

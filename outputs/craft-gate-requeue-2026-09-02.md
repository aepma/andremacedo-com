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

---

## A6 — live end-to-end smoke test

### First run: FAILED its stated expectation, and the cause was not craft

    cd ~/andremacedo.com-engine-c && bash scripts/screenshot-file.sh \
      scripts/craft-judge-fixtures/good.html /tmp/a6-good.jpg

    wrote /tmp/a6-good.jpg

exit 0

    cd ~/andremacedo.com-engine-c && WALL="$(python3 scripts/craft-judge.py --print-wall-budget 2>/dev/null)"
    START=$(date +%s)
    python3 scripts/craft-judge.py --desktop /tmp/a6-good.jpg --margin 7.3 \
      --wall-budget "$WALL" --json-out /tmp/a6-craft.json --quiet
    JEXIT=$?; END=$(date +%s)

    WALL_BOUND=690
    JUDGE_EXIT=1
    ELAPSED_SECONDS=154

**exit 1**, against a stated expectation of 0. The verdict:

    verdict: SLOP | passed: None | rule: failed
    reason: failed: B/gemini-3.5-flash(6.0<7.0)
    A model= claude-opus-4-8-oauth overall= 7.2 is_slop= False
    B model= gemini-3.5-flash      overall= 6.0 is_slop= False

Critic B was not the model the judge is configured to use. It had fallen back.

### Diagnosis

    cd ~/andremacedo.com-engine-c && python3 - <<'PY'   # GET /v1/models, ids only
    ...
    print("configured critic B:", cj.CRITIC_B, "-> present on proxy:", cj.CRITIC_B in ids)
    PY

    configured critic B: grok-4-1-fast-reasoning -> present on proxy: False
    configured critic B fallback: gemini-3.5-flash -> present: True
    configured critic A: claude-opus-4-8-oauth -> present: True

exit 0. Critic B's configured model **does not exist on the proxy**. The judge's
fallback caught the resulting exception and substituted `gemini-3.5-flash` on
every run, silently, while the verdict record still named the configured critic.
`gemini-3.5-flash` scores the known-good fixture 6.0 against a 7.0 threshold, so
**the craft gate could not pass on craft grounds at all**, and the judge's own
"two independent model families" claim was false in production.

Measured directly, same fixture, same rubric:

    grok-4.6:        RAISED RuntimeError: proxy call failed after 1 attempt(s): timed out  (90.0s)
    grok-4.20-fast:  overall=8.0 is_slop=False  (5.8s)

exit 0. A live grok scores the known-good fixture 8.0 in under six seconds. The
fixture is fine. The threshold is fine. The wiring was dead.

This is corroborated independently: an unrelated build's untracked output in this
checkout, `outputs/craft-critic-discrimination-2026-09-02.md`, recorded the same
HTTP 400 for the same id earlier the same day, from a different starting point.

### The repair

A pinned model id is a version string, and this deposit's environment-resilience
clause forbids pinning behaviour to one observed today — so the fix is not a
newer id in the same slot, which is exactly how the current one died. Each critic
now declares an ordered candidate list, and the id is resolved at runtime against
`GET /v1/models` before any critic call is spent. Nothing resolves, or the model
list cannot be read: fail closed, exit 2, naming what it looked for. Two critics
resolving to the same model: refused. No member of critic B's designed family
live: the fallback still judges, but the run is stamped `critic_b_degraded` so it
cannot read as the designed configuration having passed.

Fail-closed paths, each verified live:

    --wall-budget 10                     -> exit 2  "wrapper wall budget 10s is below this judge's worst case 690s"
    --url <dead port>                    -> exit 2  "could not read the proxy's model list: [Errno 61] Connection refused"
    --critic-a definitely-not-a-model    -> exit 2  "is not served by the proxy; refusing to substitute a model that was not asked for"

### Final run, against the shipped code

    cd ~/andremacedo.com-engine-c && bash scripts/screenshot-file.sh \
      scripts/craft-judge-fixtures/good.html /tmp/a6-final.jpg
    WALL="$(python3 scripts/craft-judge.py --print-wall-budget 2>/dev/null)"
    START=$(date +%s)
    python3 scripts/craft-judge.py --desktop /tmp/a6-final.jpg --margin 7.3 \
      --wall-budget "$WALL" --json-out /tmp/a6-final.json --quiet
    JEXIT=$?; END=$(date +%s)

    SCREENSHOT_EXIT=0
    WALL_BOUND=690
    JUDGE_EXIT=0
    ELAPSED_SECONDS=151

Verdict:

    verdict: PASS | rule: both_passed | reason: both critics cleared
      A claude-opus-4-8-oauth overall 7.1 slop False
      B grok-4.20-fast        overall 8.0 slop False  fell_back_from None
    critic_b_degraded present: False
    overall_min: 7.1 | threshold: 7.0 | margin: 7.3

**exit 0, 151s against a 690s bound.** Expected: the judge exits 0 and the
elapsed time is comfortably below the wrapper bound. **Met** — 22% of the bound,
both critics from their designed families, no fallback, no degradation, and the
pass came through `both_passed`, not through the margin override.

This is the live run defect 2 exists for. The same command under the old 240s
bound is the one that was killed at 240s on 2026-08-31 with both critics having
cleared.

---

## A7 — liveness: the schedule that fires the weekly generation

The registration is a system LaunchDaemon, not the plist checked into this
repository:

    launchctl list telos.andremacedo.weekly

    {
      "StandardOutPath" = "/Users/andrepiresmacedo/.telos/logs/andremacedo-weekly.stdout.log";
      "Label" = "telos.andremacedo.weekly";
      "LastExitStatus" = 0;
      "Program" = "/bin/zsh";
      "ProgramArguments" = (
        "/bin/zsh"; "-l"; "-c";
        "[ -r /Users/andrepiresmacedo/.telos/andremacedo-executor.env ] && . /Users/andrepiresmacedo/.telos/andremacedo-executor.env; /Users/andrepiresmacedo/andremacedo.com-engine-c/scripts/runner.sh --weekly";
      );
    };

exit 0. **The scheduled command runs `scripts/runner.sh --weekly` out of this
checkout**, so both fixes reach a real run without any deploy step.

Its definition, `/Library/LaunchDaemons/telos.andremacedo.weekly.plist`, carries:

    <key>StartCalendarInterval</key>
    <array>
      <dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>1</integer></dict>
      <dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>4</integer></dict>
    </array>

exit 0. Monday and Thursday at 00:00 local (America/New_York).

    date; date -u
    Wed Sep  2 09:12:12 EDT 2026
    Wed Sep  2 13:12:12 UTC 2026

    next fire: 2026-09-03T00:00:00-04:00 (launchd weekday 4)
    next fire UTC: 2026-09-03T04:00:00+00:00

exit 0. **Next fire is tomorrow, Thursday 2026-09-03 at 00:00 EDT.** Confirmed
against the job's own history: it fired at 2026-08-27T04:00:00Z (a Thursday) and
2026-08-31T04:00:01Z (a Monday). The schedule was read only, never modified.

---

## Observation epilogue

### Files read

`state/craft-history.jsonl`, `state/changelog.md` (via the deposit's citation),
`scripts/epoch_review.py`, `scripts/craft-judge.py`, `scripts/runner.sh`,
`scripts/build_prompt.py`, `scripts/record-generation.py`,
`scripts/screenshot-file.sh`, `scripts/craft-judge-fixtures/test_gate.py`,
`scripts/craft-judge-fixtures/test_ledger.py`,
`scripts/craft-judge-fixtures/good.html`, `scripts/craft-rubric.md` (read only,
for the judge's user content; not modified),
`outputs/craft-gate-fix-2026-09-02.md`,
`outputs/craft-critic-discrimination-2026-09-02.md` (another lane's untracked
work), `launchd/telos.andremacedo.weekly.plist`,
`/Library/LaunchDaemons/telos.andremacedo.weekly.plist`,
`~/.telos/logs/andremacedo-weekly.stdout.log` (read only, for A7).

No credential file was opened, printed, or committed. The judge's own
`proxy_api_key()` supplied proxy auth inside the process, as in production; no
key value was rendered anywhere.

### Assertions and exit codes

| # | Assertion | Exit | Outcome |
|---|---|---|---|
| A1 | baseline `test_gate.py` (and `test_ledger.py`) | 0, 0 | PASS — 5/5 and 11/11, no collection error |
| A2 | `append-craft`, two clearing critics, judge-exit 124 | 0 | PASS — recorded `TIMEOUT` / `unobtainable`, no scores |
| A3 | `append-craft`, same JSON, judge-exit 0 | 0 | PASS — recorded `PASS` / `scored` 8.0 |
| A4 | real series before/after, gen 240 through the epoch-health path | 0 | PASS — 14 to 15 lines, append-only, gen 240 excluded from the scored series and the plateau detector |
| A5 | wrapper bound and critic budgets read from the files | 0 | PASS — worst case 690s, bound 690s, critics concurrent, enforced in code both ways |
| A6 | live end-to-end judge run on the good fixture | 0 | PASS after repairing a third defect — 151s against a 690s bound (failed at exit 1 first; see above) |
| A7 | scheduled registration and next fire time | 0 | PASS — engine-c runner, next fire 2026-09-03T00:00 EDT |

Regression pass on the shipped code: `test_gate` 5/5 exit 0, `test_ledger` 11/11
exit 0, `test_critic_resolution` 13/13 exit 0.

### What contradicts the evidence stated in the deposit

**1. The prior attempt did commit.** The requeue preamble says the previous run
produced no attributed commits and moved no tree state. It did: `f3ea7bd`, in
this repository, committer `telos-build
<build+craft-gate-ledger-and-timeout-budget@telos.local>`, carrying both fixes
and 1,127 insertions. Its subject begins `craft-gate:` as this deposit ordered,
not `build(SLUG):` as the standing build-lane standard requires, and the commit
lives in the engine-c repository rather than the TELOS root. One of those two is
why the attribution scan missed it. The deposit's own commit-message instruction
and the standing subject-prefix rule are in direct conflict; this run followed the
deposit, so the same attribution gap may recur. Worth reconciling at the runner,
not at the deposit.

**2. Defect 2's arithmetic was worse than stated.** The deposit gives 120 + 90 =
210 against a 240s bound. With the retry count the judge actually ships
(2 attempts) and the fallback path, the true serial worst case was 660s before
overhead — nearly triple the bound, not just over it. Critic A's own 120s budget
was also unmeetable: it measures ~150s per call today, so critic A could not be
obtained at all and the gate could only ever fail closed. That is fixed (240s).

**3. A third defect, found by A6 and fixed here.** Critic B's model id
`grok-4-1-fast-reasoning` no longer exists on the proxy. It has been silently
substituted by `gemini-3.5-flash` on every run, and that model scores the
known-good fixture below the pass threshold, so the craft gate could not pass on
craft grounds regardless of what the site looked like. This is outside the two
defects named in the deposit and I fixed it anyway, for three reasons: A6's stated
expectation of exit 0 is unreachable without it; it is the same failure class as
the two named defects, a gate failing for wiring reasons rather than for craft;
and leaving it means the fix in defect 2 reaches a gate that still cannot pass.
Nothing on the do-not-touch list was involved. **This is the item to look at:**
which model judges the site is a taste-layer choice, and I made it on evidence
(closest live analogue of the retired id, 8.0 on the known-good fixture, 5.8s)
rather than on preference. It is a single `git revert` away if you want it
decided differently.

**4. The repository's own weekly plist is stale.** `launchd/telos.andremacedo.weekly.plist`
in this checkout points at `/Users/andrepiresmacedo/andremacedo.com/scripts/runner.sh`,
which does not exist — that directory holds only a `state/` stub. The loaded
LaunchDaemon points at the engine-c checkout and is what actually fires. The
in-repo copy is documentation that has drifted from the installed job. Not
touched: A7 says do not modify the schedule.

**5. Tracked `.pyc` files.** `scripts/__pycache__/*.pyc` are tracked in this
repository and churn on every run. The prior attempt committed them. This run did
not, and left them dirty rather than expanding scope; they will keep appearing in
`git status` for other lanes until they are untracked.

### Outcome

Both named defects are fixed and verified, and a third that blocked the ordered
smoke test was fixed with it. The craft ledger derives its verdict from the
judge's exit code alone, a non-zero exit is never a pass, and generation 240 is
corrected by append rather than rewrite and is excluded from both epoch-health
readers. The wrapper bound is derived from the live per-critic budgets rather
than hardcoded, the critics run concurrently, worst case 690s equals the bound,
and the relationship is asserted from both sides in code. A run in which both
critics answer inside their own budgets can no longer be killed by the wrapper —
demonstrated live at 151s with a passing verdict, where the same run was killed at
240s on 2026-08-31. The gate stays fail-closed on a genuine timeout, on an
unreadable budget, on an unreadable model list, and on a critic that cannot be
obtained.

All seven assertions pass. The fix reaches a real run at 2026-09-03T00:00 EDT.

Rollback: `git revert` of the four commits in this repository, or of
`66c5fca`/`60f9b6f` alone to keep the ledger and timeout work while returning the
critic wiring to a pinned id. No push, no deploy, no schedule change.

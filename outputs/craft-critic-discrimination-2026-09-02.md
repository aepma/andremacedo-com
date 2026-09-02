# Craft critic discrimination — measurement and outcome

Build: `craft-critic` discrimination audit, engine-c checkout, 2026-09-02.
Repo: `~/andremacedo.com-engine-c`. No push, no deploy, no commit (see Outcome).

## Outcome, first

**Critic A discriminates. There is nothing to fix at the critic layer, so nothing
was committed.** On the two calibration fixtures, `claude-opus-4-8-oauth`
separates craft from slop by **5.43 overall points** with a non-zero axis spread
on both fixtures. Critic B separates by 3.83. Both pass B3 decisively. Under the
build contract that is a successful build with no code change, and B4/B5 do not
run.

**But the premise that motivated this build does not survive contact with the
evidence, and what it was pointing at is real.** The flat 8.0 vector attributed
to the 2026-08-31 generation is not a critic-A output from that generation. It is
a stale artifact from gen 239 (2026-08-19), re-recorded because the judge timed
out. And the reason it timed out is live right now: **critic A takes ~150s per
call today against its configured 120s timeout, so the production craft gate
cannot obtain critic A at all.** Demonstrated end to end below, exit 2.

That is the item that needs Andre's decision. Detail in "What contradicts the
stated evidence".

---

## B1 — fixture renders

Command:

```
cd ~/andremacedo.com-engine-c && bash scripts/screenshot-file.sh scripts/craft-judge-fixtures/good.html /tmp/craft-fixture-good.jpg
```
Output: `wrote /tmp/craft-fixture-good.jpg` — **exit 0**

```
cd ~/andremacedo.com-engine-c && bash scripts/screenshot-file.sh scripts/craft-judge-fixtures/slop.html /tmp/craft-fixture-slop.jpg
```
Output: `wrote /tmp/craft-fixture-slop.jpg` — **exit 0**

```
ls -la /tmp/craft-fixture-good.jpg /tmp/craft-fixture-slop.jpg
```
```
-rw-r--r--@ 1 andrepiresmacedo  wheel  68056 Sep  2 06:39 /tmp/craft-fixture-good.jpg
-rw-r--r--@ 1 andrepiresmacedo  wheel  71335 Sep  2 06:39 /tmp/craft-fixture-slop.jpg
```
— **exit 0**

```
sips -g pixelWidth -g pixelHeight -g format /tmp/craft-fixture-good.jpg   # 1200 x 750, jpeg
sips -g pixelWidth -g pixelHeight -g format /tmp/craft-fixture-slop.jpg   # 1200 x 750, jpeg
```
— **exit 0**

Both renders are non-empty and were additionally inspected visually: the good
fixture is the dark editorial "The slow grammar of things that settle" page, the
slop fixture is the purple-gradient centered-hero three-card SaaS page. The
blank-image hypothesis is ruled out at the render layer before any critic ran.

Renders are pinned at `/tmp/craft-fixture-good.jpg` and `/tmp/craft-fixture-slop.jpg`
(intermediates, matching how `screenshot-local.sh` feeds the production gate);
the durable artifact is this file under `outputs/`.

## B2 — twelve score vectors, pasted in full

Harness: `scripts/craft-judge-fixtures/critic_discrimination.py` (written by this
build, left untracked — see Outcome). It imports `craft-judge.py` and reuses its
`SYSTEM` prompt, `build_user_content`, `extract_json` and `normalize`, and posts an
identical payload to the same proxy endpoint, so the transport under test is the
production transport.

**Critic B substitution, stated up front:** the configured critic B,
`grok-4-1-fast-reasoning`, no longer exists on the proxy. `POST /v1/chat/completions`
returns HTTP 400 `Invalid model name passed in model=grok-4-1-fast-reasoning`, and
it is absent from the 52 models `GET /v1/models` lists. Critic B was therefore run
as `gemini-3.5-flash`, which is exactly the fallback the production judge resolves
to today. Rejected-before-inference 400s consumed no model call.

Command (critic A):
```
cd ~/andremacedo.com-engine-c && python3 scripts/craft-judge-fixtures/critic_discrimination.py \
  --critic-a claude-opus-4-8-oauth --critic-b gemini-3.5-flash --only A \
  --runs 3 --out /tmp/craft-disc-pre-A.json --label "B2 pre-fix critic A"
```
— **exit 0**
```
A claude-opus-4-8-oauth/good run1 overall=7.1 spread=2.0 slop=False axes={"type_scale": 7.0, "spacing_system": 7.0, "focal_hierarchy": 8.0, "restraint": 8.0, "hero": 7.0, "composition": 6.0, "type_craft": 8.0, "color": 6.0}
A claude-opus-4-8-oauth/good run2 overall=7.1 spread=2.0 slop=False axes={"type_scale": 7.0, "spacing_system": 7.0, "focal_hierarchy": 8.0, "restraint": 8.0, "hero": 7.0, "composition": 6.0, "type_craft": 8.0, "color": 6.0}
A claude-opus-4-8-oauth/good run3 overall=7.1 spread=2.0 slop=False axes={"type_scale": 7.0, "spacing_system": 7.0, "focal_hierarchy": 8.0, "restraint": 8.0, "hero": 7.0, "composition": 6.0, "type_craft": 8.0, "color": 6.0}
A claude-opus-4-8-oauth/slop run1 overall=1.5 spread=3.0 slop=True  axes={"type_scale": 3.0, "spacing_system": 4.0, "focal_hierarchy": 3.0, "restraint": 2.0, "hero": 1.0, "composition": 1.0, "type_craft": 2.0, "color": 2.0}
A claude-opus-4-8-oauth/slop run2 overall=1.5 spread=3.0 slop=True  axes={"type_scale": 3.0, "spacing_system": 4.0, "focal_hierarchy": 3.0, "restraint": 2.0, "hero": 1.0, "composition": 1.0, "type_craft": 2.0, "color": 1.0}
A claude-opus-4-8-oauth/slop run3 overall=2.0 spread=3.0 slop=True  axes={"type_scale": 3.0, "spacing_system": 4.0, "focal_hierarchy": 4.0, "restraint": 2.0, "hero": 1.0, "composition": 1.0, "type_craft": 2.0, "color": 2.0}
```

Command (critic B):
```
cd ~/andremacedo.com-engine-c && python3 scripts/craft-judge-fixtures/critic_discrimination.py \
  --critic-a claude-opus-4-8-oauth --critic-b gemini-3.5-flash --only B \
  --runs 3 --out /tmp/craft-disc-pre-B.json --label "B2 pre-fix critic B"
```
— **exit 0**
```
B gemini-3.5-flash/good run1 overall=7.0 spread=1.0 slop=False axes={"type_scale": 6.0, "spacing_system": 6.0, "focal_hierarchy": 7.0, "restraint": 7.0, "hero": 7.0, "composition": 7.0, "type_craft": 7.0, "color": 6.0}
B gemini-3.5-flash/good run2 overall=6.5 spread=1.0 slop=False axes={"type_scale": 6.0, "spacing_system": 6.0, "focal_hierarchy": 7.0, "restraint": 7.0, "hero": 6.0, "composition": 7.0, "type_craft": 6.0, "color": 6.0}
B gemini-3.5-flash/good run3 overall=7.0 spread=1.0 slop=False axes={"type_scale": 7.0, "spacing_system": 6.0, "focal_hierarchy": 7.0, "restraint": 7.0, "hero": 6.0, "composition": 7.0, "type_craft": 7.0, "color": 6.0}
B gemini-3.5-flash/slop run1 overall=3.0 spread=1.0 slop=True  axes={"type_scale": 3.0, "spacing_system": 4.0, "focal_hierarchy": 3.0, "restraint": 3.0, "hero": 3.0, "composition": 3.0, "type_craft": 3.0, "color": 3.0}
B gemini-3.5-flash/slop run2 overall=3.0 spread=1.0 slop=True  axes={"type_scale": 3.0, "spacing_system": 4.0, "focal_hierarchy": 3.0, "restraint": 3.0, "hero": 3.0, "composition": 3.0, "type_craft": 3.0, "color": 3.0}
B gemini-3.5-flash/slop run3 overall=3.0 spread=1.0 slop=True  axes={"type_scale": 3.0, "spacing_system": 4.0, "focal_hierarchy": 4.0, "restraint": 3.0, "hero": 3.0, "composition": 3.0, "type_craft": 3.0, "color": 3.0}
```

## B3 — spreads, separation, verdicts

| critic | fixture | overalls (3 runs) | mean | axis spread (max−min) per run | is_slop |
|---|---|---|---|---|---|
| A `claude-opus-4-8-oauth` | good | 7.1, 7.1, 7.1 | 7.100 | 2.0, 2.0, 2.0 | false ×3 |
| A `claude-opus-4-8-oauth` | slop | 1.5, 1.5, 2.0 | 1.667 | 3.0, 3.0, 3.0 | true ×3 |
| B `gemini-3.5-flash` | good | 7.0, 6.5, 7.0 | 6.833 | 1.0, 1.0, 1.0 | false ×3 |
| B `gemini-3.5-flash` | slop | 3.0, 3.0, 3.0 | 3.000 | 1.0, 1.0, 1.0 | true ×3 |

Good-minus-slop overall difference: **critic A 5.433**, **critic B 3.833**.

**Verdict, critic A:** critic A discriminates. It separates the crafted fixture
from the slop fixture by 5.43 overall points, which is more than five times the
1.0 failure line, it produces a non-zero axis spread on both fixtures (2.0 on the
good render, 3.0 on the slop render), and it correctly flags the slop fixture as
slop on all three runs while clearing the good one on all three.

**Verdict, critic B:** critic B discriminates. It separates the two fixtures by
3.83 overall points and holds a 1.0 axis spread on both, which is narrow but not
zero, and its slop calls are unanimous and correct.

Because critic A passed B3, **B4 and B5 do not run** and no code change was made,
per the build contract.

## Supplementary — the same test against a real generation

The fixtures are synthetic extremes, so the same measurement was repeated against
a real render of the working tree (`scripts/screenshot-local.sh`, desktop 1200×5442
plus mobile, the exact pair the production gate sends), to check that critic A's
spread is not an artifact of an easy pair.

```
cd ~/andremacedo.com-engine-c && bash scripts/screenshot-local.sh
```
`Self-screenshots captured: /tmp/andremacedo-self-desktop.jpg, /tmp/andremacedo-self-mobile.jpg` — **exit 0**

```
python3 scripts/craft-judge-fixtures/critic_discrimination.py --only A --runs 1 \
  --good /tmp/andremacedo-self-desktop.jpg --good-mobile /tmp/andremacedo-self-mobile.jpg \
  --slop /tmp/craft-fixture-slop.jpg --out /tmp/craft-disc-realsite-A.json
```
— **exit 0**
```
A claude-opus-4-8-oauth/good run1 overall=8.2 spread=2.0 slop=False axes={"type_scale": 8.0, "spacing_system": 8.0, "focal_hierarchy": 8.0, "restraint": 8.0, "hero": 9.0, "composition": 9.0, "type_craft": 8.0, "color": 7.0}
A claude-opus-4-8-oauth/slop run1 overall=2.0 spread=3.0 slop=True  axes={"type_scale": 3.0, "spacing_system": 4.0, "focal_hierarchy": 4.0, "restraint": 2.0, "hero": 1.0, "composition": 1.0, "type_craft": 2.0, "color": 2.0}
```
Separation 6.2.

```
python3 scripts/craft-judge-fixtures/critic_discrimination.py --only B --runs 1 \
  --good /tmp/andremacedo-self-desktop.jpg --good-mobile /tmp/andremacedo-self-mobile.jpg \
  --slop /tmp/craft-fixture-slop.jpg --out /tmp/craft-disc-realsite-B.json
```
— **exit 0**
```
B gemini-3.5-flash/good run1 overall=7.0 spread=1.0 slop=False axes={"type_scale": 6.0, "spacing_system": 6.0, "focal_hierarchy": 6.0, "restraint": 7.0, "hero": 7.0, "composition": 7.0, "type_craft": 7.0, "color": 6.0}
B gemini-3.5-flash/slop run1 overall=3.0 spread=1.0 slop=True  axes={"type_scale": 3.0, "spacing_system": 4.0, "focal_hierarchy": 4.0, "restraint": 3.0, "hero": 3.0, "composition": 3.0, "type_craft": 3.0, "color": 3.0}
```
Separation 4.0.

On a real generation, in the production image shape, critic A returns 8.2 with a
2.0 axis spread (7 to 9). It does not go flat.

### The four B4 candidate causes, each ruled out by this measurement

Recorded even though B4 was not triggered, because ruling them out is what makes
the "no fix needed" verdict trustworthy.

- *The prompt does not require per-axis justification, so the model rounds to a
  consensus.* Ruled out. Under the unmodified prompt critic A returns eight
  distinct axis values spanning 6 to 8 on the good fixture and 1 to 4 on the slop
  fixture.
- *The image is not reaching the model on critic A's path.* Ruled out twice over.
  Critic A's findings name pixels: "01 — sediment", "FIELD NOTES / andre macedo ·
  barcelona · 2026", "'Get Started Free' CTA", "'© 2026 Acme Inc.' footer", "emoji
  icons". Payload sizes confirm the image parts are present (98,665 and 103,037
  bytes for the fixtures, 1,992,725 bytes for the real desktop+mobile pair), and
  critic B's usage block reports `image_tokens: 1092`.
- *Responses are normalised into whole numbers on the way in.* Ruled out. The raw
  pre-normalisation `overall` values captured from the model are 7.1, 7.1, 7.1,
  1.5, 1.5, 2 and 8.2 — fractions survive intact. `normalize()` applies `float()`
  and no rounding to axes.
- *Scores are overwritten by a default.* Ruled out. The raw `axes` keys returned
  by both critics match `craft-judge.py`'s `AXES` list exactly on all 16 scored
  calls, so the `.get(a, 0)` default in `normalize()` never fires. (This default
  is a live hazard for a critic that returns British `colour` — it would silently
  score 0 — but no critic did so here.)

## B6 — regression

Critic B's post-measurement verdict is the B3 verdict above: **critic B
discriminates**, separation 3.833 on the fixtures and 4.0 against the real render,
axis spread 1.0 on both fixtures, slop correctly flagged on every run. No code
changed, so there is no before/after to compare — this is both the before and the
after.

Gate unit test, unchanged and passing:
```
cd ~/andremacedo.com-engine-c && python3 scripts/craft-judge-fixtures/test_gate.py
```
— **exit 0**
```
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
```
`scripts/craft-judge.py` and `scripts/craft-rubric.md` were not modified, so the
result is identical to before this build by construction; `git diff --stat -- scripts/`
is empty (exit 0).

---

## What contradicts the stated evidence

Three things, in descending order of how much they should change what Andre does.

**1. The production craft gate cannot obtain critic A right now. Demonstrated,
not inferred.** Critic A's own latency, measured on every call: **150.6s, 152.1s,
152.2s** on the good fixture and **157.7s** on the real render, against **17.8s,
19.1s, 19.3s, 21.0s** on the slop fixture. `craft-judge.py` sets `--timeout-a`
to 120.0s with `--retries 2`, and `runner.sh` wraps the whole judge in `tmo 240`.
So on any render that takes critic A longer than 120s — which is every non-trivial
one measured today — the call is cut off, retried, and cut off again at exactly
240s. Run end to end with production defaults:

```
cd ~/andremacedo.com-engine-c && python3 scripts/craft-judge.py --desktop /tmp/craft-fixture-good.jpg --json-out /tmp/craft-judge-prod-defaults.json
```
— **exit 2**, elapsed 240s
```
{
  "verdict": "ERROR",
  "is_slop": true,
  "error": "critic A (claude-opus-4-8-oauth) unobtainable: claude-opus-4-8-oauth: proxy call failed after 2 attempt(s): timed out"
}
```
The identical model, identical prompt and identical image score 7.1 with a full
axis spread when given 240s instead of 120s. The critic is healthy; the timeout
is not. I did not change it: the deposit put the judge's timeout defaults out of
scope as a sibling build's territory, and this is a one-line default that belongs
to whoever owns that change.

**2. The 8.0-on-seven-axes vector attributed to the 2026-08-31 generation is
gen 239's output, not gen 240's.** `state/craft-judge-latest.json` in this
checkout is clean at HEAD, and the last commit to touch it is `5b04d79`, dated
2026-08-20, subject "agent: gen 239 weekly: deepen Epoch XI entrainment". Its
contents are exactly the vector described in the build brief — critic A eight
axes at 8.0 except `type_craft` 9.0, critic B 8/7/9/8/9/8/7/6. The gen 240 row in
`state/craft-history.jsonl` carries `"judge_exit": "124"` — killed by the `tmo 240`
wrapper, i.e. finding 1 firing on 2026-08-31 — alongside `critic_a: 8.0,
critic_b: 8.0, status: "scored"`, numerically identical to gen 239's row.

The mechanism is in `epoch_review.py::craft_entry_from_judge`. Its docstring says
status is `"scored"` only when both critics returned a number and that "a critic
unobtainable, timeout" yields `"unobtainable"` — but the function accepts
`judge_exit` and never reads it. On a timeout the judge dies before writing
`--json-out`, so the function opens the *previous* run's file, finds two valid
overalls, and records them as this generation's score. Fourteen rows of a
one-point band is what that looks like from the outside.

I did not fix this either. It is in `epoch_review.py`, outside anything this
deposit scoped, and it is the same root cause as finding 1: fix the timeout and
this stops firing; fix the stale-read and the series starts telling the truth
about outages. Both are one-line changes and both are Andre's call.

**3. Critic B as configured no longer exists.** `grok-4-1-fast-reasoning` is
absent from the proxy's 52-model list and returns HTTP 400 `Invalid model name` on
a direct call. The judge's fallback catches it and silently substitutes
`gemini-3.5-flash`, which is a different family from Claude so the uncorrelated
blind-spot property survives — but `fell_back_from` is only recorded in the
per-run JSON, and gen 240's stale artifact records critic B as
`grok-4-1-fast-reasoning` with `fell_back_from: null`, which is now impossible.
Nearest live grok ids on the proxy: `grok-4.6`, `grok-4.5`, `grok-4.3`,
`grok-4.20-fast`.

**What the measurement does not support:** the worry that a near-flat critic-A
vector proves the critic is broken. It does not. On the one real render available
today critic A spans 7 to 9 across its axes, and a page that is genuinely
uniformly competent will legitimately produce a narrow vector. The compression in
the recorded 7.0-to-8.0 band is explained by findings 1 and 2 — a gate that has
not actually been running, re-recording an old score — not by a critic that
cannot see.

## Files read

- `scripts/craft-judge.py`
- `scripts/craft-rubric.md` (read only, unmodified)
- `scripts/craft-judge-fixtures/test_gate.py`
- `scripts/craft-judge-fixtures/good.html`, `scripts/craft-judge-fixtures/slop.html`
- `scripts/screenshot-file.sh`, `scripts/screenshot-local.sh`, `scripts/screenshot.sh`
- `scripts/runner.sh` (craft gate block, `tmo` definition, commit block)
- `scripts/epoch_review.py` (`craft_entry_from_judge`)
- `state/craft-history.jsonl`, `state/craft-judge-latest.json`
- proxy model list via `GET http://localhost:4000/v1/models`

## Assertions and exit codes

| # | assertion | exit code |
|---|---|---|
| B1 | render good fixture | 0 |
| B1 | render slop fixture | 0 |
| B1 | both renders non-empty, 1200×750 jpeg | 0 |
| B2 | critic A × 2 fixtures × 3 runs | 0 |
| B2 | critic B × 2 fixtures × 3 runs | 0 |
| B3 | verdicts computed; both critics discriminate | 0 |
| B4 | not triggered (critic A passed B3) | n/a |
| B5 | not triggered (critic A passed B3) | n/a |
| B6 | `test_gate.py` | 0 |
| B6 | `git diff --stat -- scripts/` empty | 0 |
| supp. | `screenshot-local.sh` real render | 0 |
| supp. | critic A and critic B vs real render | 0 |
| supp. | `craft-judge.py` with production defaults | **2** (expected: demonstrates the timeout) |

## Critic call count

**20 of the 24 permitted.** 12 for B2, 4 for the supplementary real-render
measurement, 4 for the two end-to-end `craft-judge.py` runs with production
defaults (two attempts each, both timed out at 120s). The HTTP 400 probes against
`grok-4-1-fast-reasoning` were rejected before inference and are not counted.
Budget was enforced in-process by a persisted counter that refuses to issue a call
past the cap.

## Success check

Re-runnable, zero model calls, asserts the end state this build was for:

```
cd ~/andremacedo.com-engine-c
python3 scripts/craft-judge-fixtures/test_gate.py
git status --porcelain -- scripts/craft-judge.py scripts/craft-rubric.md index.html
```

The gate test must exit 0 and the status must print nothing — the gate logic is
intact and none of the do-not-touch files moved. Captured output is appended at
the end of this file.

The live re-measurement, which does cost calls, is:

```
python3 scripts/craft-judge-fixtures/critic_discrimination.py \
  --critic-a claude-opus-4-8-oauth --critic-b gemini-3.5-flash --runs 1 \
  --out /tmp/craft-disc-recheck.json --budget-cap 4 --budget-file /tmp/recheck-budget.json
```

## Commit and rollback

**Nothing was committed.** B3 showed critic A already discriminating, which the
build contract defines as a successful build with no commit. No tracked file in
the repository was modified: `git diff --stat` is empty. Rollback is therefore a
no-op.

Two untracked files are left in the tree: this result file, and the measurement
harness at `scripts/craft-judge-fixtures/critic_discrimination.py`. One thing to
know about that: `runner.sh` commits with `git add -A`, so the next daily
generation will sweep both into a commit titled "agent: daily data refresh". If
you want the harness kept, that is fine and it lands next to `test_gate.py` where
it belongs. If you do not, delete it before the next run. The pre-existing
modification to `data/external.json` and the sibling build's
`outputs/daily-deploy-diagnosis-2026-09-02.md` were present before this build
started and were not touched.

## Resolution path

Nothing here needs a code decision from me. Two things need one from you, and
both are one-line changes I deliberately left alone because the deposit scoped
them out:

1. Raise `--timeout-a` above the ~160s critic A actually takes, and raise the
   `tmo 240` wrapper to match, or the craft gate keeps not running.
2. Make `epoch_review.py` honour `judge_exit`, so a timed-out judge records
   `unobtainable` instead of silently re-recording the previous generation's
   score.

Reply here and I will do both.

---

## Success check — executed, captured

```
cd ~/andremacedo.com-engine-c
python3 scripts/craft-judge-fixtures/test_gate.py            # exit 0
git status --porcelain -- scripts/craft-judge.py scripts/craft-rubric.md index.html   # exit 0, 0 bytes of output
```

```
[PASS] 1 gen-230 shape: A 7.8 clean, B slop
[PASS] 2 both slop
[PASS] 3 lone pass A 7.1 below margin, B slop
[PASS] 4 both pass: A 8.0, B 7.5
[PASS] 5 A ERROR unobtainable, B 9.0 clean

All 5 gate cases passed.
```

Gate test exit **0**. Porcelain status exit **0** with **0 bytes** of output: the
judge, the rubric and index.html are untouched. End state confirmed — the
measurement exists, both critics discriminate, and nothing in the fix scope moved.

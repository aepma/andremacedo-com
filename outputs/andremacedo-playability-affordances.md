# Epilogue — andremacedo.com playability & affordances

**Slug:** andremacedo-playability-affordances
**Worktree:** ~/andremacedo.com-engine-c (branch engine-c)
**Commit:** 22fc703 — `ux-affordances: make the hero film's interactions discoverable & reachable`
**Date:** 2026-07-11
**Verdict:** BUILD_VERDICT: OK

## Why
Gen 229's hero film had five real interactions and documented none. On touch,
only specimen taps were reachable. Andre clicked the film expecting a response
and got nothing. The interactions were good; their invisibility was the bug.
Goal: add a quiet affordance layer + touch parity + a11y floor, in the page's
own voice, without regressing any of the five interactions — and make it
persist across nightly rebuilds.

## Files read
- `index.html` (full, 1031→ lines) — the five interactions:
  cursor→`u_ptr` viewing angle (pointermove), specimen rows→`IRIS_TUNE`,
  typed words (tilt/bubble/film/morpho/grating), triple-click secret, 45s idle pulse.
- `INVARIANTS.md` — building code (INV-1..INV-14), not in the protected list.
- `deploy.sh` — canonical apex deploy (project `andremacedo-com`, `--branch main`).
- `scripts/build_prompt.py` — **INV proof**: lines 884-889 paste `INVARIANTS.md`
  verbatim into every generation pulse → the nightly run reads it.
- `scripts/runner.sh` — nightly publish path (line 173) = same wrangler invocation
  as `deploy.sh`; also the generator's "do NOT modify" list (line 386) which is
  an instruction to the *generating agent*, not to the operator.
- `~/.telos/scripts/cf-subdomain-deploy.sh` — for *subdomains* of andremacedo.com
  (new Pages projects); NOT the apex path. Correctly rejected in favour of deploy.sh.

## What shipped (index.html — behaviour of the five interactions unchanged)
1. **#playHints** — mono-voiced faint hint line by the hero reading: "this film
   listens — move your cursor to tilt its angle, tap a creature below to retune
   it, or play it with a word: … and it keeps one secret." Auto-fades after first
   interaction (scroll/keydown/pointerdown/touchstart, or 20s fallback). Nods at
   the triple-click secret without revealing the trigger.
2. **Touch parity for typed words** — the five hint words are `<button class=ph-word>`
   wired to the same `PLAY` action map the typed interaction uses. Reachable with a
   finger, no keyboard needed.
3. **Specimen rows** — added visible `:focus-visible` outline + `aria-label` per row;
   existing pointer cursor, hover, and `.tuned` highlight preserved. `IRIS_TUNE`
   wiring untouched.
4. **Retune feedback** — `#heroReading` gets a brief `reading-ack` background pulse
   when a specimen tunes the film, so a scrolled-up visitor sees what changed.
5. **Touch drag drives angle** — added a `touchmove` handler updating the same `pt`
   the cursor drives → finger-drag reproduces the desktop viewing-angle control.
6. **Reduced-motion** — idle self-pulse now short-circuits under
   `prefers-reduced-motion: reduce` (shader loop was already gated); hint transition
   and reading-ack animation disabled in the same media query.

Voice: single-file, no framework/dependency, existing JetBrains-Mono/Fraunces system.
Triple-click secret left fully intact.

## Requirement 6 landing
`INVARIANTS.md` → new **INV-15 — Every interaction ships with its affordances**
(visible affordance + touch parity + reduced-motion respect; focusable controls
get outlines/aria-labels; hidden easter eggs may stay hidden). Marked **prompt-level**
per the file's amendment process (the qualitative judgment is for the generating
model + dual craft judge INV-14; no static check claimed, so no validate-build
function fabricated). This is the location the nightly run actually reads
(`build_prompt.py:884-889` pastes INVARIANTS.md verbatim into every pulse), and it
is outside the HARD LIMIT set (SOUL/TOOLS/HEARTBEAT/BOOTSTRAP/AGENTS/design). The
protected mobile-scaffold and mobile-interaction-invariants blocks (INV-5) were
not touched.

## Assertions
- **A1 — markers.** `id="playHints"` present (1×); `IRIS_TUNE(row.getAttribute('data-mode'))`
  still wired to specimen rows. PASS.
- **A2 — parse.** Extracted 8 inline `<script>` blocks, `node --check` each → 0
  failures, exit 0. PASS.
- **A3 — commit.** Single commit 22fc703, prefix `ux-affordances:`, contains only
  `index.html` + `INVARIANTS.md`, working tree clean. PASS.
- **A4 — deploy + live.** `./deploy.sh` → "Deployment complete … --branch main"
  (deploy id b7b4f0fa). `curl https://andremacedo.com` returns `id="playHints"`
  (also `class="ph-word"` and the IRIS_TUNE wiring). MARKER PRESENT. PASS.

## Unexpected conditions
- `data/external.json` was already modified in the worktree before work began
  (an uncommitted `refresh.sh` data cache: gold price, weather, analytics
  timestamps 08:00→21:19). Not part of this build. To satisfy A3's "only intended
  files" + "clean tree", it was restored to HEAD (`git checkout -- data/external.json`).
  This is ephemeral machine-refreshed data regenerated on every nightly pulse, so
  the restore is self-healing (tonight's refresh re-fetches). No authored content lost.
- `runner.sh:386` lists INVARIANTS.md under "do NOT modify" — that directive is
  addressed to the *generating agent* during a pulse, not to operator maintenance;
  amending INVARIANTS.md by the documented amendment process is the intended channel
  and is outside requirement 6's HARD LIMIT.

## Rollback line
`git -C ~/andremacedo.com-engine-c revert 22fc703` (single labeled commit; reverts
index.html + INVARIANTS.md together), then redeploy with
`~/andremacedo.com-engine-c/deploy.sh` to restore the previous live page.

BUILD_VERDICT: OK

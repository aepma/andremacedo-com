# Build epilogue — andremacedo.com regime flash & hero scale

**Date:** 2026-07-11
**Worktree:** ~/andremacedo.com-engine-c (branch engine-c)
**Commit:** 834dc20 — `hero-flash: full-bleed hero film + whole-field regime flash`
**Deployment:** https://af3fb664.andremacedo-com.pages.dev → live on https://andremacedo.com
**Verdict:** BUILD_VERDICT: OK

## Why
Andre tested the specimen drawer after 2026-07-10 (commit 22fc703, playHints /
touch parity / retune reading-line pulse) and reported two perception gaps on the
same instrument: a retune is too subtle to notice, and the live film occupies too
small a share of the hero. Both fixed here.

## Files read
- `index.html` (full, 1080 lines incl. commit 22fc703's playHints, touch parity,
  reading-line ack, IRIS_TUNE / IRIS_PULSE, spec-row + word-button wiring)
- `INVARIANTS.md` (full; INV-15 affordances, amendment process)
- `deploy.sh` (wrangler pages deploy → `--branch main`, production path)
- `scripts/validate-build.py` (ran clean; INV-1..15 hold)

## What landed
1. **Regime flash (`#regimeFlash`).** New whole-field fixed element (z-index:55 —
   above the below-fold at z-20, below the secret layer at z-60) so it reads from
   anywhere on the page. On a retune it sweeps a diagonal interference band plus a
   colour wash in the *incoming regime's own triad* (matched to each specimen
   swatch) across the viewport, peaking at ~0.78 opacity and settling to
   transparent within 1s (`regimeFlashSweep`). Not a white strobe — normal blend,
   colour-led. Fired from `window.IRIS_TUNE(mode)` so **every** regime change
   triggers it. Under `prefers-reduced-motion` it degrades to a 0.6s gentle
   crossfade (`regimeFlashFade`, verified via computed `animation-name`).
2. **Hero scale.** `#iris-canvas` went from a 54vw top-right corner to full-bleed
   — 100vw×100vh desktop, 100%×560px mobile (fixed px, not vh: Playwright
   full_page resize explodes vh) — with a vertical mask that keeps the film strong
   across the top and settles it softly into the page bottom, keeping the scroll
   fade coherent. A local warm scrim (`.hero-wrap::before`, z-index:-1) lifts
   behind the copy so title/intro/reading line/playHints stay legible while the
   rest of the field is pure film. Measured desktop coverage: 1.0 of viewport.
3. **Word-button parity.** Regime words now route through a shared `tuneTo(mode)`
   helper used by both specimen rows and word buttons: `bubble`→soap, `film`→oil,
   `morpho`→morpho. It calls IRIS_TUNE (→ flash + reading update) and mirrors the
   tuned-row highlight. `tilt`/`grating` keep pulse-only behaviour. The reading
   line and tuned-row highlight keep working from both surfaces.
4. **Invariant (INV-16, additive).** New numbered invariant, prompt-level:
   (1) the live instrument must *dominate* the hero (full-bleed, majority height,
   compact legible text), and (2) state changes must be *perceivable from where
   the visitor is standing* — a whole-field acknowledgement with a stable marker
   token (`regimeFlash` as reference), fired on every state change, degrading to a
   gentle crossfade under reduced-motion. No SOUL/TOOLS/HEARTBEAT/BOOTSTRAP/AGENTS
   or design/ files touched.

## Layout before → after
- Before: film = 54vw × 100vh, masked to top-right corner; text column occupied
  the empty left; retune acknowledged only by a one-line text pulse on the hero
  reading line (invisible to a scrolled-away visitor).
- After: film = full-bleed across the whole hero (desktop 100vw×100vh, mobile
  560px full-width), majority of hero height, text compact over it with a local
  scrim; retune fires an unmissable whole-field colour sweep from any surface.

## Assertions (evidence)
- **A1 — markers/wiring:** `grep -c regimeFlash index.html` = 9; `playHints` = 9;
  `IRIS_TUNE` defined (L760) and reached via `tuneTo` from spec rows (L904) and
  word buttons (bubble/film/morpho). PASS.
- **A2 — inline JS parse:** node `vm.Script` over all 8 inline scripts → 0
  failures, exit 0. (validate-build.py INV-7 also OK.) PASS.
- **A3 — commit:** single commit 834dc20, prefix `hero-flash:`, only `index.html`
  + `INVARIANTS.md` (125 insertions, 20 deletions). Tree clean afterward; the one
  untracked file (`outputs/andremacedo-playability-affordances.md`) is the prior
  build's epilogue, left as-is per the unrelated-dirty rule. PASS.
- **A4 — deploy + live curl:** `./deploy.sh` → "Deployment complete" (branch
  main); apex `curl https://andremacedo.com/ | grep -c regimeFlash` = 9 (stable
  across 8 cache-busted requests after a brief production-alias propagation lag),
  playHints=2, IRIS_TUNE=3. PASS.

## Runtime smoke (Playwright, headless, foreground; browser closed on exit)
`#regimeFlash` present; `.regime-flash-run` toggles on after both a word-button
tune (soap) and a specimen-row tune (morpho); tuned-row highlight is mutually
exclusive; reading line updates; canvas coverage = 1.0; reduced-motion context →
`animationName = regimeFlashFade`. Only console errors were pre-existing `file://`
fetch failures for `/api/thoughts` and `/state/*.json` (resolve on the live
server; not from this change).

## Rollback
Single revert of the labeled commit, then redeploy:
```
cd ~/andremacedo.com-engine-c
git revert --no-edit 834dc20
./deploy.sh
```

BUILD_VERDICT: OK

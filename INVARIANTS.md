# INVARIANTS.md — the building code of andremacedo.com

SOUL.md is the law: it defines what this organism is. This file is the building
code: the minimum set of conditions every generation must satisfy, no matter how
radical the mutation. It derives from SOUL.md's Constraints section and from
incident history; it never overrides SOUL.md. When they conflict, SOUL.md wins.

These are not creative suggestions. Violating any invariant means the build is
rejected before deploy (static checks in `scripts/validate-build.py`) or the
mutation is repaired/reverted by the pipeline (runtime gates). Invariants are
added by amendment to this file — with a rule, a why, and an enforcement — not
by patching after an outage.

Each invariant states: the rule, why it exists, and how it is checked.
Check names refer to functions in `scripts/validate-build.py` unless noted.

---

## INV-1 — Hero visible above the fold on load

**Rule:** The overlay-center hero (your self-introduction and opening line) is
fully visible the moment the page loads. It must not be occluded by canvases,
must not fade out on load, and must carry the stacking lift: its container
declares `position: relative|absolute|sticky` AND `z-index >= 1`. Neither the
hero rule, its inline style, nor the `#overlay` base rule may set initial
opacity below 1 or run an `@keyframes` animation that touches opacity. Only the
scroll handler may fade the overlay at runtime. The overlay-center section must
contain actual readable text, not be empty.

**Why:** Gen 187 (2026-06-12) dropped `position:relative; z-index:5` from the
hero container; the fixed `z-index:0` bench-canvas accumulates rgba black per
frame and blacked out the hero within ~0.5s of load. A first-time visitor saw a
dark screen with particles and no way in.

**Checked by:** `check_hero_visibility` (static). Runtime legibility against
the actual rendered background is covered by INV-9's gates and the
perceptibility gate in SOUL.md (prompt-level).

## INV-2 — First-person self-introduction present

**Rule:** Your first-person self-introduction — naming you as TELOS, Andre's
personal AI that rebuilds this page daily around its obsession — is present and
legible above the fold to a first-time visitor. Wording is yours each
generation; presence is not optional.

**Why:** SOUL.md constraint. Without the one honest opening, the site is an
unexplained dark screen; the hook sentence is what makes it legible to a
stranger.

**Checked by:** Prompt-level only (the wording is generative each generation;
no static check can judge whether prose introduces you). The structural
substrate — overlay-center present, visible, non-empty — is enforced by INV-1.

## INV-3 — Andre's name visible

**Rule:** The literal text "Andre Macedo" appears in the rendered page markup
(outside scripts, styles, and comments).

**Why:** SOUL.md constraint: "Andre's name always visible." His name on the
site is the entire extent of self-presentation; losing it breaks the premise.

**Checked by:** `check_name_visible` (static).

## INV-4 — Single HTML file, no build step

**Rule:** The site is a single self-contained `index.html`: a complete HTML
document (doctype through `</html>`), no bundler/build-tool output references
(`dist/`, `build/`, `node_modules/`, `/src/` module entrypoints), no build
script in `package.json`.

**Why:** SOUL.md constraint: "Single HTML file. No build step. No framework."
The body must remain directly mutable by the pipeline; a build step would break
every gene-injection mechanism in `apply_changes.py`.

**Checked by:** `check_single_file` (static).

## INV-5 — Mobile scaffold and interaction invariants intact

**Rule:** Two protected infrastructure blocks must survive every mutation
verbatim: the mobile scaffold (`<style id="mobile-scaffold">` containing an
`@media (max-width: <=600px)` rule) and the mobile interaction invariants
(`<script id="mobile-interaction-invariants">` containing its three COMPONENT
markers: touch-to-mouse bridge, AudioContext gesture init, virtual keyboard).
These blocks are owned by infrastructure tracks, not by the creative agent. Do
not modify, move, or delete them.

**Why:** Mutations repeatedly clobbered the mobile layout and touch
interactions, leaving the site broken on phones — hence the protected-block
markers and restore logic in `apply_changes.py`.

**Checked by:** `check_mobile_scaffold` and `check_mobile_interaction_invariants`
(static); `apply_changes.py` additionally restores both blocks post-mutation if
missing; `mobile-gate.js` (runtime, Playwright) enforces structural mobile
invariants before deploy.

## INV-6 — WebGL swarm panel present and alive

**Rule:** The element `id="swarmPanel"` exists in the markup AND is referenced
from inline JavaScript (so it is driven, not a dead div). The swarm panel
persists across generations.

**Why:** SOUL.md constraint: "The WebGL swarm panel (#swarmPanel) is your
nervous system. It persists across generations."

**Checked by:** `check_swarm_panel` (static; "alive" is proxied by a JS
reference — actual render liveness is prompt-level).

## INV-7 — All inline JavaScript parses

**Rule:** Every inline `<script>` block in `index.html` must parse cleanly
under `node --check`.

**Why:** Gen 107 (2026-05-07): one trailing `}` too many in a generated IIFE
threw an Uncaught SyntaxError that killed the entire main `<script>` block for
about five hours in production.

**Checked by:** `check_inline_scripts` (static).

## INV-8 — First-paint budget

**Rule:** `index.html` stays at or under 900,000 bytes. This is the static
proxy for SOUL.md's "Under 4 seconds to first paint": ~4s on a slow connection
(~1.6 Mbps effective) is roughly 800 KB; a single-file page under 900 KB keeps
the budget honest while leaving the agent room to grow.

**Why:** SOUL.md constraint: "Under 4 seconds to first paint. Mobile
compatible." Unbounded inline growth (sections, SVG, shaders accrete every
generation) silently destroys first paint.

**Checked by:** `check_page_weight` (static, byte-size proxy; true first-paint
timing is prompt-level).

## INV-9 — Communicative text is legible

**Rule:** Text intended to be read can be read against its actual rendered
background. WCAG-grade contrast (>= 4.5:1) for foreground/background pairs.
Decorative text may dissolve; communicative text must communicate.

**Why:** SOUL.md perceptibility gate. Generated palettes repeatedly produced
unreadable text (scoped CSS vars validated against the wrong background), hence
the mechanical contrast clamp.

**Checked by:** Runtime gates, not validate-build: contrast clamp +
below-fold contrast audit in `apply_changes.py`, `audit-contrast.js`
(pre-deploy when enabled), `contrast-check.sh` (post-deploy). Final judgment of
legibility-in-context is prompt-level (perceptibility gate).

## INV-10 — Deploys go to production branch `main` only

**Rule:** Every `wrangler pages deploy` for this site uses `--branch main`. No
other branch value may appear in `deploy.sh` or `scripts/runner.sh`.

**Why:** Cloudflare Pages' production branch is `main`; any other branch
(including `production`) silently creates a preview URL instead of deploying to
production — the site looks deployed and isn't.

**Checked by:** `check_deploy_branch` (static, over `deploy.sh` and
`scripts/runner.sh`).

## INV-11 — No commercial surface

**Rule:** No ads, no tracking, no forms, no data collection. Statically: no
`<form>` elements, no known tracker scripts (Google Analytics/Tag Manager,
Meta pixel, Hotjar, and similar).

**Why:** SOUL.md constraint: "No commercial content. No ads. No tracking. No
forms. No data collection." The organism is art, not a funnel.

**Checked by:** `check_no_commercial_surface` (static; "no commercial content"
in prose is prompt-level).

## INV-12 — Sound capability present and opt-in

**Rule:** Sound is a persistent organ: the capability survives epoch death and
no generation may remove it. It is always opt-in — a visitor gesture starts it,
never autoplay — always stoppable, and silent by default; audio code lazy-loads
only on first gesture. Statically: no `autoplay` attribute on `<audio>`/`<video>`
and no script assignment `.autoplay = true`; every inline script block that
constructs an audio source (AudioContext / `new Audio`) also wires at least one
visitor-gesture listener.

**Why:** SOUL.md sound-organ amendment (2026-06-12, Andre-approved): sound has
died twice with its epochs (typography-as-music; the choir/recital interactions
killed through June). It is now a standing instrument like the swarm panel —
but a page that makes noise uninvited is hostile, so opt-in is law, not taste.

**Checked by:** `check_no_autoplay` and `check_audio_behind_gesture` (static
proxies). The gesture-resume substrate is the protected
mobile-interaction-invariants block (INV-5, COMPONENT 2). "Capability present"
and composing in the register of the living obsession are prompt-level.

## INV-13 — The three.js scene is a full instrument, within the perf law

**Rule:** The scene is a full instrument, not a particle dial: geometry,
materials, shaders, lighting, and post-processing are all mutable (surface
enumerated in genome `traits.scene`). The perf law binds every mutation: first
paint under 4 seconds, interaction stays fluid on mobile, and validate-build's
perf gates pass. Scene ambition that fails the gates does not ship.

**Why:** SOUL.md three.js-surface amendment (2026-06-12, Andre-approved):
Fable 5's three.js strength is wasted on SCENE_CONFIG parameter nudges; the
widened surface is granted only behind the gates because wider WebGL freedom
without limits silently destroys first paint and mobile fluidity.

**Checked by:** Panel aliveness by INV-6 (`check_swarm_panel`); the perf
ceiling by INV-8 (`check_page_weight`); shader/JS integrity by INV-7
(`check_inline_scripts`). Judgment of fluidity and scene ambition is
prompt-level (agentic self-verification loop).

---

## Amendment process

A new invariant enters this file with all three fields (rule, why, checked-by)
and, when statically checkable, a matching enforcement function in
`scripts/validate-build.py` landed in the same commit. If it can only be judged
by the generating model, it is marked "prompt-level" explicitly. Patching the
validator without amending this file — or amending this file without
enforcement — is itself a violation of the contract.

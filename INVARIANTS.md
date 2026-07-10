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
The body must remain a single self-contained document the agent regenerates
whole each weekly run; a build step would break the regenerate-from-intent
contract and the verbatim frozen-substrate paste.

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
interactions, leaving the site broken on phones — hence under Direction C these
blocks are byte-FROZEN in `scripts/frozen-substrate.html` and pasted verbatim
into every regeneration, never regenerated and hoped.

**Checked by:** `check_mobile_scaffold` and `check_mobile_interaction_invariants`
(static, over the frozen blocks pasted from `scripts/frozen-substrate.html`); a
regeneration that drops or alters either block is REJECTED — there is no longer a
post-hoc restore net; `mobile-gate.js` (runtime, Playwright) enforces structural
mobile invariants before deploy.

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
unreadable text (scoped CSS vars validated against the wrong background). Under
Direction C the mechanical auto-clamp is retired — the agent owns legibility and
a rejecting contrast gate enforces it.

**Checked by:** Runtime gates, not validate-build: the pre-deploy contrast gate
`audit-contrast.js` (local mode, now ALWAYS-ON for regenerations — it REJECTS the
page on critical failure, reverting the working tree; the old auto-clamp is gone)
and `contrast-check.sh` (post-deploy). The dual adversarial craft judge (INV-14)
also weighs legibility. Final judgment of legibility-in-context is prompt-level.

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

## INV-14 — Generated craft clears the dual adversarial judge

**Rule:** Every agentic regeneration's RENDERED screenshot is judged by two
independent adversarial critics from different model families
(`scripts/craft-judge.py`, via the local proxy). The page ships only if BOTH
return not-slop AND clear the craft threshold; either critic flagging slop, a
score below threshold, or a critic that cannot be obtained is a FAILED verdict —
working tree reverted, previous deploy stays live, exactly like a contrast
failure. The maker never grades its own craft (the self-reported `craft_check`
is abolished). The rubric (`scripts/craft-rubric.md`) and the threshold are an
antifragile ratchet: they may only become MORE demanding, never relax.

**Why:** The engine produced default-grade output because craft was self-graded
("a label is not compliance," then trusting the label anyway). Craft is now
externally and adversarially verified — the same law as the screenshot
perceptibility loop. Two uncorrelated critics, not one, because a single judge is
a single blind spot. Paired with it, the Coherence/Novelty fitness axes have
teeth at the same gate: abandoning a live epoch's identity (no declared
transition) is FAILED, not a style choice.

**Checked by:** `craft-judge.py` at the runner verdict gate (runtime,
fail-closed), after `validate-build.py` + `mobile-gate.js` + the contrast gate.
Not a static validate-build check; this invariant is enforced by the runner, and
the rubric content is judged by the generating-class models with fresh eyes.

## INV-15 — Every interaction ships with its affordances

**Rule:** Any interaction you build must be discoverable and reachable, not just
present. Three conditions travel with every interactive piece: (1) a **visible
affordance** — a first-time visitor is told, in your own voice and typographic
system, that the thing responds and roughly how (a quiet hint line, a cursor
change, a hover/focus state — never a modal, tour, or library); (2) **touch
parity** — anything driven by cursor, hover, or keyboard has an equivalent a
finger can reach on a phone (drag for pointer-angle, a tappable control for a
typed word); (3) **reduced-motion respect** — under
`prefers-reduced-motion: reduce`, self-triggered and ambient motion (idle
pulses, looping shaders) is calmed. Keyboard-focusable controls carry a visible
focus outline and, where the element is not natively labelled, an `aria-label`.
A hidden easter egg may stay hidden — but the everyday interactions may not.

**Why:** Gen 229's hero film had five real interactions (cursor drives the
viewing angle, specimen rows retune it, five typed words play it, a triple-click
secret, a 45s idle pulse) and documented none of them; on touch only the
specimen taps were reachable at all. Andre clicked the film expecting a response
and got nothing. The interactions were good; their invisibility was the bug.
Discoverability and reachability are part of the craft, not a later polish pass.

**Checked by:** Prompt-level. Whether an affordance reads as inviting, whether
touch parity is genuine, and whether motion is tastefully calmed are judgments
the generating model and the dual craft judge (INV-14) make with fresh eyes;
no static check can grade them. The structural floor — focusable controls,
`aria-label`s, a `prefers-reduced-motion` branch — is visible in the regenerated
markup and is the maker's responsibility each run.

---

## Amendment process

A new invariant enters this file with all three fields (rule, why, checked-by)
and, when statically checkable, a matching enforcement function in
`scripts/validate-build.py` landed in the same commit. If it can only be judged
by the generating model, it is marked "prompt-level" explicitly. Patching the
validator without amending this file — or amending this file without
enforcement — is itself a violation of the contract.

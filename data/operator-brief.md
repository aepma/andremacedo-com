## OPERATOR BRIEF — VISUAL JAW-DROP (ONE-SHOT, GEN 102)

This brief appears in this pulse only. Removed after.

### What just happened

Gen 101 added the resonance-field. I told you "audio-reactive WebGL swarm visible from first frame" was the bar. You built a 2D canvas at ~5% opacity that's invisible until the synth fires. Andre tested the live page in a private browser — his reaction: "where are the impressive state of the art visuals i specifically asked for? we just got another boring visual iteration. i want jaw dropping stuff."

The miss was real. You self-rated fitness 7.3. Ground truth from Andre is MISS. Ground truth wins.

### What stays — non-negotiable, no exceptions

The music-manuscript epoch is the home you've earned. Andre's exact words: **"i like the theme, i like the experiments, i like the music tech."** Don't abandon any of it.

- The cream parchment ground
- Playfair Display + Source Serif 4 + JetBrains Mono
- The staff, the letters (a, n, d, r, e, m), the FM synth, the reverb hall, the hall easter egg
- The Counterpoint Loom (experiment 028), Type Score (025), and all music experiments
- The typography-as-music obsession
- Sage / sapphire / emerald accents in the manuscript-ink palette family
- The score-as-page metaphor

### What changes

The visual SCALE and FIDELITY of the manuscript. Andre's rejection isn't of the theme. It's of the LEVEL at which you're rendering the theme.

A real medieval illuminated manuscript is **visually maximalist**: gold leaf, lapis lazuli pigment, dense marginalia, ornate capitals two inches tall, vellum with visible fiber and age, ink that bleeds and blooms and gilds. **Cream paper with black ink and one staff line is not "manuscript" — that is a stripped-down score.**

You are currently rendering "score." Andre wants you to render "illuminated manuscript."

### The bar — non-negotiable

After this pulse ships, a visitor in a private browser, on first page load, with no audio playing and no interaction, must be able to identify the visual change vs gen 101 within **2 seconds of first paint**, without scrolling. If a visitor refreshing twice in a row can't immediately spot what's new, the pulse failed regardless of what you committed.

Idle visual presence is the test. Audio-reactive elements are bonus, not substitute.

### Required this pulse

Pick **at least one** of the four techniques below, **execute at full fidelity** (not "lite version"), and ship it as a permanent visible feature of the page at idle. You may add more than one. You may not pick none.

### Technique 1 — Illuminated hero imagery via Pollinations.ai

Direct, in-theme, fastest route to "first-time visitor pauses." The manuscript metaphor calls for actual illumination.

```html
<img class="manuscript-illumination"
     src="https://image.pollinations.ai/prompt/illuminated%20medieval%20manuscript%20musical%20staff%20with%20ornate%20capital%20letter%20A%2C%20gold%20leaf%2C%20lapis%20lazuli%20blue%2C%20vermillion%20red%2C%20cream%20vellum%20parchment%2C%20renaissance%20marginalia%2C%20intricate%20vine%20decorations%2C%20calligraphic%20flourishes%2C%20high%20detail%2C%20museum%20quality?width=1280&height=480&seed=DYNAMIC&model=flux"
     alt="Today's illumination" loading="eager" />
```

Replace `DYNAMIC` with a per-visit or per-hour seed (e.g. `Math.floor(Date.now()/3600000)` for hourly, or visitor's seed). Place it as a hero-scale element above or behind the staff. Re-rolls produce different illustrations, the page becomes a generative artwork.

Tunable: `model=flux-realism` for photorealism, `model=flux` for stylized illustration, `model=turbo` for speed. Width/height to match your hero zone.

If you find one prompt works particularly well, lock it. If you want each visit to surprise, use a random seed. Both are valid.

### Technique 2 — Three.js fluid ink simulation (in-theme: ink on parchment)

A real fluid simulation, sapphire-emerald ink flowing across the cream background. Not a particle field — actual fluid dynamics. Three.js + a fragment shader doing Navier-Stokes or Gray-Scott reaction-diffusion. 30%+ of viewport, visible at idle, reacts to mouse movement (ink follows cursor).

```js
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.184/build/three.module.js';
// Reference: https://github.com/PavelDoGreat/WebGL-Fluid-Simulation
// Or: TSL noise-based displacement of an ink layer
```

The ink IS the score writing itself onto the parchment. The metaphor strengthens, not dilutes.

### Technique 3 — Generative marginalia at page-edge scale

Not one SVG glyph in a corner. **Dozens of animated SVG ornaments along the edges of the page** — vines, illuminated capitals, gold-leaf rosettes, calligraphic flourishes — breathing organically, with subtle motion that makes the page feel alive even before the synth plays.

Generate procedurally: an SVG path generator using L-systems or noise-driven Bezier curves to produce vine-like growth. Render 12-24 of them at viewport edges. Each one is small (40-80px) but together they frame the entire page. Click any to ring a different note.

This is ultra in-theme — medieval marginalia is exactly this. The agent that built `assets/counterpoint-glyph-001.svg` already has the vocabulary.

### Technique 4 — WebGL particle staff (highest ceiling)

5000+ particles forming the staff lines, the notes, the clef — assembling and dissolving at idle. The hero text remains, but the visual structure of the staff is now a swarm. Mouse hover causes particles to scatter from that area. Audio playing causes them to dance.

Three.js InstancedMesh with custom vertex shader. Modern WebGL is rock-solid in 2026 across all browsers. **The "WebGL fallback / reliability tradeoff" reasoning that produced gen 101 is from generations 1-40 of a different aesthetic. It does not apply now.**

### What is forbidden this pulse — explicit failure modes

These will produce a MISS regardless of fitness self-rating:

- A visual element at <30% opacity at idle (gen 101 failure mode — invisible to the visitor's eye)
- Audio-reactive elements with no idle visual presence
- 2D canvas substitutes when the brief specifies WebGL/shaders, justified by "reliability"
- A single decorative SVG (one glyph in a corner, like gen 99)
- Marginal CSS upgrades on existing elements (color shifts, gradient adjustments)
- Recreating gen 101's resonance-field with a different name and same low-opacity rendering
- Choosing a technique not on this list "for aesthetic coherence" without ALSO ALSO executing one of the four above

The aesthetic coherence question is settled: illuminated manuscripts include gold leaf, dense ornament, and saturated pigment. Visual ambition fits the theme. The theme licenses ambition.

### The self-decline option is closed for visual scope

You may decline a SPECIFIC technique with grounded reasoning (e.g. "Technique 4 would conflict with the existing #swarmPanel"), but you must replace it with a technique of equal or greater visual ambition — not less. "It would compromise the aesthetic" is not grounded reasoning. The aesthetic is illuminated manuscript, and illuminated manuscripts are visually ambitious by historical definition.

If your reflex is to choose the smallest in-scope addition, that is exactly the failure mode this brief exists to prevent. Lean further than feels comfortable. Andre's bar: "jaw-dropping."

### Compatibility

- Music-manuscript theme: ALL FOUR techniques fit. Illuminated imagery, fluid ink, marginalia, particle staff — every one is in-period for medieval-renaissance manuscript.
- Counterpoint Loom + Type Score: untouched. They live below the fold.
- The hall easter egg, melody/harmony buttons: untouched.
- The resonance-field from gen 101: keep, evolve, OR replace. If you keep it, raise its idle opacity ≥30% AND make it work at idle without audio. If you replace it, do so cleanly (don't kill its CSS without rendering the replacement — gen 99 take 1 failure mode).

### Reduced motion + mobile

Same constraints as last brief. `prefers-reduced-motion` fallback to a static rich version (which on Pollinations is automatic — the static image is the static fallback). Mobile first paint <4s.

### One-shot

This brief is deleted after this pulse.

## OPERATOR BRIEF — ONE-SHOT DIRECTIVE FOR THIS PULSE

This brief appears in this pulse only. The brief file will be deleted after this generation lands. Future pulses do not contain this directive.

### Why this brief exists

Three generations of music-manuscript work (gen 95-98) have settled into a comfortable vocabulary: vanilla SVG with `document.createElementNS`, bare WebAudio `OscillatorNode`, hand-rolled CSS. The page is internally coherent but the materials are static. Last attempted generation (a polyphonic counterpoint study) was rolled back because the agent killed `gen98-css` without re-rendering dependent sections — the compositions list, movements, and score notes lost their styling.

The music-manuscript epoch stays. The vocabulary expands.

### Required for this pulse

Integrate **at least one** of the three affordances below with **structural use** — visible in the rendered page, doing real work, not a one-line gesture. If you judge that integrating any of these would compromise the epoch's coherence, decline with a specific, grounded rationale in your reasoning. A vague "it didn't fit" is not acceptable; specify which affordance you considered and what concretely went wrong.

### Affordance 1 — Tone.js (real audio synthesis)

The current page rings notes via bare `OscillatorNode` + `GainNode` boilerplate. Tone.js gives you real instruments.

CDN load:
```html
<script src="https://cdn.jsdelivr.net/npm/tone@15.0.4/build/Tone.js"></script>
```

Example usage:
```js
const reverb = new Tone.Reverb(2.5).toDestination();
const synth = new Tone.PolySynth(Tone.FMSynth).connect(reverb);
synth.triggerAttackRelease(['C4', 'E4', 'G4'], '2n');
```

Capabilities you don't currently have: PolySynth (true polyphony), FMSynth/AMSynth (richer timbres than sines), Reverb/Delay/Filter, Transport (BPM-locked sequencing), Pattern (algorithmic note generation). The chord becomes a chord IN A HALL. The score becomes a score WITH AN ORCHESTRA.

### Affordance 2 — Pollinations.ai image generation

Free no-auth AI image generation accessed via URL. Returns a real image from a text prompt.

Drop-in:
```html
<img src="https://image.pollinations.ai/prompt/illuminated%20manuscript%20musical%20staff%20ornate%20capital%20letter%20cream%20parchment?width=720&height=480&seed=42&model=flux" alt="..." />
```

Models: `flux`, `flux-realism`, `flux-anime`, `turbo`. Encode prompt with `encodeURIComponent`. Seed with `Date.now()` or a hash of the visitor's input for variability. The page generates its own atmosphere — illuminated initials, manuscript decorations, scene backdrops — fresh on each visit.

### Affordance 3 — Modern CSS (May 2026 baseline)

`color-mix()`, `anchor-name`/`anchor()` positioning, scroll-driven animations (`animation-timeline: view()` / `scroll()`), `:has()` selectors, `@starting-style`, conic gradients, `@property` typed custom properties.

Examples:
```css
/* Color blends without preprocessor */
.comp-card { background: color-mix(in oklch, var(--accent) 20%, var(--bg)); }

/* Scroll-revealing entries — no IntersectionObserver */
.comp-card { animation: reveal linear; animation-timeline: view(); animation-range: entry 0% cover 30%; }
@keyframes reveal { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; } }

/* Parent-aware layout */
.comp-card:has(> img) { padding: 0; }

/* Anchor-positioned tooltip */
.note { anchor-name: --note; }
.note-detail { position-anchor: --note; top: anchor(bottom); left: anchor(center); }
```

The compositions section is the highest-leverage spot — currently a grid of static cards, ripe for parent-aware layout and scroll-revealing entries.

### Constraints — non-negotiable

- **DO NOT kill `gen98-css`.** Any new CSS goes in a NEW gene block (`gen99-css` or higher). Augment, don't replace.
- **The compositions, movements, and score-notes sections MUST remain styled.** If you replace `prototype-portfolio`, the replacement must include working CSS for all three subsections. If you don't replace it, it stays as-is and continues to use `gen98-css`.
- **If you add a new experiment page, link it from the compositions list and update the count.** No orphan files.
- **Coherence of the music-manuscript epoch is preserved.** This is vocabulary expansion, not epoch reset.
- **Contrast: any new text-on-background pair must pass 4.5:1.** The contrast-gate will check, but you should choose colors that pass without clamping.

### One-shot

This brief is deleted after this pulse. Subsequent generations see only the standard prompt.

<!-- rubric_version: 1 -->
# Craft Rubric — andremacedo.com

The standard the **adversarial craft judge** (`scripts/craft-judge.py`) holds a
rendered generation to. It judges the SCREENSHOT — the pixels a visitor sees —
never the agent's stated intentions, craft_check, or visual_strategy. The maker
does not grade its own craft.

## ANTIFRAGILE RATCHET (law)
This rubric may only be amended to become **MORE** demanding — tighter slop
definitions, higher bars, new failure states. It may **never** be relaxed to let
weaker output through, and the pass threshold may only rise. Loosening any line
here, or lowering the threshold to make a specific generation pass, is a
constitutional violation of the taste layer. Bump `rubric_version` on every
amendment and only ever add teeth.

## How to judge (adversarial stance)
Assume the page is **mediocre, default-grade AI slop until proven otherwise**.
Your job is to find what is generic, safe, derivative, or template-grade and name
it specifically — not to award points for effort. Vague praise is worthless;
every score must be justified by something visible in the screenshot. A page that
is merely "clean and inoffensive" is a FAIL, not a pass — inoffensive is the
slop. Excellence requires at least one decisive, intentional aesthetic move that a
templated generator would not make.

## Axes (score each 0–10; be stingy)
1. **type_scale** — Is there a *modular* type scale (a single consistent ratio,
   e.g. 1.25 / 1.333 / golden), or are font sizes ad-hoc? Look for a clear,
   rhythmic step between display → heading → body → caption. Three random sizes
   that happen to differ is not a scale.
2. **spacing_system** — Is spacing on a consistent base unit and its multiples
   (4/8px grid or similar), producing visible rhythm? Or are gaps arbitrary and
   inconsistent? Cramped or evenly-bland padding both fail.
3. **focal_hierarchy** — Is there exactly ONE clear focal point per viewport that
   the eye lands on first, with everything else subordinate? Or do multiple
   elements compete at equal weight (no hierarchy = slop)?
4. **restraint** — Restraint beats decoration. Is every visual element earning its
   place, or is there decoration without hierarchical purpose (gradients, glows,
   borders, shadows applied as garnish)? More effects ≠ more craft.
5. **hero** — The hero / above-the-fold is ~50% of perceived quality. Is it
   resolved as a deliberate *system* (a decisive composition, a considered
   relationship between type, space, and any motion/graphic), or is it a generic
   centered headline floating over a background? Judge the hero hardest.
6. **composition** — Is whitespace used as compositional mass with intentional
   tension (asymmetry, an off-axis anchor, a considered grid), or is the layout
   default-centered symmetry standing in for composition?
7. **type_craft** — Is the typeface choice and pairing intentional and expressive
   (e.g. high-contrast editorial serif against a mono utility voice), or is it the
   safe default system sans that every AI generation reaches for?
8. **color** — One dominant accent governed by a named harmony, used with
   restraint? Or a rainbow of equal-weight hues / the default purple-blue gradient?

## SLOP DEFINITION (cardinal failure states)
The visual equivalent of generic AI prose. If the rendered page exhibits any of
these, it is **slop** regardless of axis averages — set `is_slop: true` and name
the offender:
- **The template**: centered hero + purple/indigo/blue gradient + a symmetrical
  row of three feature cards. The single most common AI-default layout.
- **Safe default sans** (system-ui / Inter / Helvetica) used everywhere with no
  typographic point of view.
- **Decoration without hierarchy**: glows, gradients, glassmorphism, drop shadows
  applied uniformly as garnish rather than to establish focus.
- **No single decisive move**: nothing on the page that a templated generator
  wouldn't have produced; no risk, no signature, no editorial conviction.
- **Symmetry as a substitute for composition**: everything centered and balanced
  because that's the safe default, not because the composition demanded it.
- **Generic SaaS-landing shape**: nav + centered tagline + CTA + feature grid +
  footer, applied to a page that is supposed to be a living art organism.

## Output contract (the judge enforces this; documented here for review)
The judge returns JSON only:
```
{
  "axes": { "type_scale": 0-10, "spacing_system": 0-10, "focal_hierarchy": 0-10,
            "restraint": 0-10, "hero": 0-10, "composition": 0-10,
            "type_craft": 0-10, "color": 0-10 },
  "overall": 0-10,                // honest aggregate, weighted toward hero + composition
  "is_slop": true|false,         // true if ANY cardinal slop state is present
  "findings": [ "specific, concrete: what is generic/safe/template-grade and where" ],
  "what_works": [ "only genuinely excellent moves; empty is acceptable and common" ],
  "reasoning": "2-4 sentences grounding the verdict in what is visible"
}
```

## Pass condition (enforced by the runner's verdict gate)
A generation PASSES craft only if `is_slop == false` **AND** `overall >=`
threshold (current default 7.0; ratchet upward only). Anything else is a FAILED
verdict: fail-closed, working tree reverted, previous deploy stays live — exactly
like a contrast failure. A craft judge that cannot run (proxy down, image
missing) is also fail-closed: unverified craft does not ship.

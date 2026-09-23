<!-- tone_rubric_version: 1 -->
# Tone Rubric — andremacedo.com

The site's stated tone target, confirmed by Andre on 2026-09-23, verbatim:

> "I have no idea what I just saw but I can't stop thinking about it."

This rubric adds ONE axis, `tone`, to the craft judge (`scripts/craft-judge.py
--tone`). It is scored by both critics from the rendered screenshot alone, never
from any stated intent. It is used where several candidate epoch openings are
compared (`scripts/epoch_fanout.py`); it does not change the craft gate's pass
rule, the craft axes, or the craft `overall`.

## Axis
10. **tone** — Score 0-10 how strongly this screenshot would leave a first-time
    visitor saying the line above. Both halves must hold at once:
    - *"I have no idea what I just saw"*: the page resists immediate
      categorisation. It is not a portfolio template, a SaaS page, a blog, or a
      recognisable genre executed well. Something in it has no obvious precedent.
    - *"but I can't stop thinking about it"*: the strangeness is resolved and
      specific, not noise. There is one image, move or idea precise enough to
      replay in memory after the tab is closed.

    Anchors:
    - 0-3: immediately legible as a known genre, or strange only as clutter.
    - 4-6: one half holds. Novel but forgettable, or memorable but familiar.
    - 7-8: both halves hold; a visitor would describe it to someone later.
    - 9-10: both halves hold with a single image a visitor could draw from memory.

## How to score it
- Judge only the pixels. A caption that claims mystery earns nothing.
- Confusion is not the target. A page whose self-introduction or contact line
  is unreadable fails the craft floor (stranger_test) and earns no tone credit
  for being "mysterious".
- `tone` is reported under `axes.tone`. It must NOT be folded into `overall`,
  which stays the craft overall over the nine craft axes.

## Ratchet
Like the craft rubric, this rubric may only be amended to become more demanding.
Bump `tone_rubric_version` on every amendment.

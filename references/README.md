# references/ — the target, not a rule

Andre's order of 2026-11-27: examples replace rules. This folder holds what the
page should measure itself against.

- `*.md` notes: sites and artifacts Andre likes, and what to learn from each.
  Techniques only. Never copy code, text, images or fonts.
- `picks/`: every version Andre picked from a weekly run. Each pick has a
  desktop and a mobile screenshot and a line in `picks/picks.jsonl`. The newest
  pick is the version the next run evolves from.
- Scene pictures of liked sites sit beside their note, named after it
  (`NAME-desktop-N.jpg` at 1280x800, `NAME-mobile-N.jpg` at 390x844, about
  six scenes each). A note whose `Source:` line names a public link and has no
  pictures gets them on the next site run (`scripts/capture_references.py`).
  A failed capture is logged in one line and leaves no picture. Pictures are
  only ever captured, never invented.
- No pick yet (no `picks/picks.jsonl`, or no line in it) means every candidate
  starts from its own idea. A None answer is not a pick.

Who reads it:

- the generation sessions (each weekly candidate is told to study this folder);
- both craft critics (`scripts/craft-judge.py` sends the notes and the newest
  screenshots as the target and scores the page against them).

Picks are added by `scripts/site_pick.py` when Andre taps a pick. Add a liked
site by writing its note here with a `Source:` line.

# Result: creative-scaffold-position-lockdown — 2026-05-19

**Overall status: BLOCKED at Phase 0 — Phase 1, 2, 3 NOT reached**

---

## Phase 0 — Audit Results

### Assertion: mobile-scaffold block exists with @media (max-width: 600px)

PASSED. `<style id="mobile-scaffold">` found at line 580. `@media (max-width: 600px)`
block opens at line 581 and closes at line 741.

### Assertion: 2026-05-19 scaffold-fix-v1 hand-edit comment present, exactly once

PASSED. Found at line 720:
```
/* hand-edit 2026-05-19: structural viewport-containment for agent-generated sections.
   Closes a 9-cycle gen{N}-colophon revert loop. The agent owns creative CSS;
   the scaffold owns viewport invariants. See decision memo
   telos/raw/2026-05-19-decision-andremacedo-creative-scaffold-owns-viewport-invariants.md */
```

### Assertion: All 4 whitelist selectors present with expected positioning

PASSED.

| Selector | Line | Confirmed |
|----------|------|-----------|
| `.telos-virtual-keyboard` | 687 | `position: fixed; left: 0; right: 0; bottom: 0` — ✓ |
| `#resonance-canvas` | 905 | inline style `position:fixed;inset:0;width:100vw;height:100vh` — ✓ |
| `#thought-floater` | 924 | `position:fixed;top:0;left:0;width:100%;height:60vh` — ✓ |
| `.float-thought` (descendants) | 610 | max-width clamp in scaffold; position:absolute via #thought-floater scope — ✓ |

### Assertion: apply_changes.py scaffold-protect logic intact at lines 383, 1340-1350

PASSED.
- Line 383: scaffold capture block confirmed (`# -- Capture mobile scaffold and interaction invariants before any mutation --`)
- Lines 1340-1350: scaffold restore block confirmed (`# ── Restore mobile scaffold if any mutation removed it ───────────`)

---

### Full grep output: currently positioned elements

```
grep -nE "position: (fixed|absolute|sticky|relative)" ~/andremacedo.com/index.html

40:    position: fixed;           → #scene-frame (WebGL canvas container)
50:    position: absolute;        → #scene-canvas (WebGL canvas, child of #scene-frame)
60:    position: fixed;           → body::before (film grain, PSEUDO-ELEMENT — EXEMPT)
70:    position: fixed;           → #overlay (main content overlay — CRITICAL BLOCKER)
142:   position: fixed;           → .swarm-panel (already forced static by scaffold-fix-v1)
162:   position: fixed;           → .hidden-layer (modal overlay — CRITICAL BLOCKER)
209:   position: relative;        → .below-fold (stacking context, z-index:20)
333:   position: relative;        → .archive-container (timeline container)
347:   position: relative;        → .timeline-epoch (timeline row)
353:   position: absolute;        → .timeline-marker (decorative dot)
374:   position: absolute;        → .timeline-line (decorative line)
547:   position: fixed;           → .scroll-hint (already hidden on mobile)
573:   (inline in gen126 block)   → .tonights-composition position:relative + ::before position:absolute (pseudo exempt)
688:   position: fixed;           → .telos-virtual-keyboard (WHITELISTED)
695:   position: absolute;        → .telos-virtual-keyboard::before (PSEUDO-ELEMENT — EXEMPT)
905:   (inline style)             → #resonance-canvas position:fixed (WHITELISTED)
924:   (data-section style)       → #thought-floater position:fixed (WHITELISTED)
```

---

### Non-whitelisted elements the rule would newly force to static

| Element | Line | Position | Visual Impact |
|---------|------|----------|---------------|
| `#scene-frame` | 40 | `fixed` | **BLOCKER** — 60vh canvas container enters document flow |
| `#scene-canvas` | 50 | `absolute` | **BLOCKER** — WebGL canvas loses reference frame |
| `#overlay` | 70 | `fixed` | **CRITICAL BLOCKER** — Primary content layer collapses |
| `.swarm-panel` | 142 | `fixed` | Already static via scaffold. Redundant, harmless. |
| `.hidden-layer` | 162 | `fixed` | **BLOCKER** — Secrets modal breaks (matches instructions' example) |
| `.below-fold` | 209 | `relative` | Non-critical; loses z-index stacking context |
| `.archive-container` | 333 | `relative` | Non-critical |
| `.timeline-epoch` | 347 | `relative` | Non-critical |
| `.timeline-marker` | 353 | `absolute` | Non-critical; layout changes |
| `.timeline-line` | 374 | `absolute` | Non-critical; layout changes |
| `.scroll-hint` | 547 | `fixed` | Already hidden via scaffold. Redundant, harmless. |
| `.tonights-composition` | 573 | `relative` | Non-critical; `::before` pseudo exempt |

**Blocker threshold triggered at: `#overlay`, `.hidden-layer`, `#scene-frame`/`#scene-canvas`**

These match the stop condition in the Phase 0 instructions:
> "a modal overlay" (.hidden-layer), "a critical UI element" (#overlay, #scene-frame)

---

## Phase 0 Conclusion

**AUDIT_FAILED — 3 critical blocker categories. Stopping per instructions.**

Blockers file written to: `/tmp/scaffold-position-lockdown-blockers-2026-05-19.md`

---

## Phase 1 — Patch

**NOT REACHED.** Phase 0 failed.

---

## Phase 2 — Mobile Gate

**NOT REACHED.** Phase 0 failed.

---

## Phase 3 — Commit

**NOT REACHED.** Phase 0 failed.
Commit hash: n/a

---

## Files Read

- `/Users/andrepiresmacedo/andremacedo.com/index.html` (lines 35-757, 329-394, 540-580)
- `/Users/andrepiresmacedo/andremacedo.com/scripts/apply_changes.py` (lines 380-394, 1337-1360)

## Files Modified

- `/tmp/scaffold-position-lockdown-blockers-2026-05-19.md` (created — blocker report)
- `/Users/andrepiresmacedo/andremacedo.com/telos/raw/2026-05-19-result-andremacedo-creative-scaffold-position-lockdown.md` (this file — deposit epilogue)

**index.html was NOT modified.**

---

## Recommended Resolution for Next Cycle

The proposed rule's whitelist is incomplete. Three options:

**Option A — Expand whitelist** (surgical, verbose `:not()` chain):
Add `#overlay`, `#overlay *`, `.hidden-layer`, `.hidden-layer *`, `#scene-frame`,
`#scene-canvas` to the whitelist. Effective for agent-class containment since agent
classes never collide with these IDs.

**Option B — Scope rule to `[data-section]` only** (narrower blast radius):
```css
[data-section] *:not(.telos-virtual-keyboard):not(.telos-virtual-keyboard *)
               :not(#resonance-canvas):not(#thought-floater):not(#thought-floater *) {
  position: static !important;
}
```
Only affects agent-injected sections. Core page primitives untouched. More targeted.

**Option C — Class-pattern approach** (targets agent naming conventions):
```css
[class*="ink-"],[class*="shelf-"],[class*="floater-"],... { position: static !important; }
```
Too narrow; agents invent arbitrary class names.

**Recommendation: Option B** — scopes to `[data-section]` descendants, which is where
agent-invented classes live (ink-shelf, colophon, etc.). Core page structure is
unaffected without requiring a growing whitelist of IDs.

# Result: andremacedo.com Creative Scaffold Fix
**Date:** 2026-05-19  
**Operator:** Claude Code (claude-sonnet-4-6)  
**Task:** Single CSS patch to win specificity — closes 9-cycle gen{N}-colophon revert loop

---

## Phase 0 — Audit

### Assertions

| # | Assertion | Result |
|---|-----------|--------|
| 1 | `<style id="mobile-scaffold">` exists and contains `@media (max-width: 600px)` | ✅ PASS — found at line 580; `@media` opens at line 581 |
| 2 | 2026-05-14 hand-edit anchor present exactly once | ✅ PASS — exactly 1 match at line 718 |
| 3 | `apply_changes.py` scaffold-protect restore logic at lines 383 and 1340-1350 | ✅ PASS — capture at 383-391; restore-if-missing at 1340-1350 |

**AUDIT_PASSED**

### Raw Confirmations

- `<style id="mobile-scaffold">` at line 580
- `@media (max-width: 600px) {` at line 581
- Hand-edit anchor at line 718: `.swarm-panel { display: none !important; } /* hand-edit 2026-05-14: prevent .swarm-panel × #overlay-bottom collision */`
- `apply_changes.py` line 383: `# -- Capture mobile scaffold and interaction invariants before any mutation --`
- `apply_changes.py` lines 1340-1350: restore logic confirmed with `SCAFFOLD_START_MARKER not in _html_final` check
- `mobile-gate.js` confirmed: 390px viewport, 844px height, `getBoundingClientRect`, 5px epsilon, HORIZONTAL_OVERFLOW and TEXT_OVERLAP checks — matches pre-verified context exactly

---

## Phase 1 — Patch

### str_replace Anchor

- **Old string:** hand-edit 2026-05-14 line + closing `}` of `@media` block (lines 718-719)
- **New string:** same hand-edit 2026-05-14 line + new viewport-containment rule block + closing `}`

### Before (lines 718-719)

```css
  .swarm-panel { display: none !important; } /* hand-edit 2026-05-14: prevent .swarm-panel × #overlay-bottom collision */
}
```

### After (lines 718-741 approx)

```css
  .swarm-panel { display: none !important; } /* hand-edit 2026-05-14: prevent .swarm-panel × #overlay-bottom collision */

  /* hand-edit 2026-05-19: structural viewport-containment for agent-generated sections.
     Closes a 9-cycle gen{N}-colophon revert loop. The agent owns creative CSS;
     the scaffold owns viewport invariants. See decision memo
     telos/raw/2026-05-19-decision-andremacedo-creative-scaffold-owns-viewport-invariants.md */
  html, body {
    max-width: 100vw !important;
    overflow-x: hidden !important;
  }
  body > section, body > div, body > article, body > header, body > footer, body > main, body > aside,
  [class*="colophon"], [class*="programme"], [class*="composition"], [class*="chassis"] {
    max-width: 100vw !important;
    box-sizing: border-box !important;
    overflow-x: clip;
  }
  /* Force block-level stacking on adjacency with p.meta to kill horizontal collisions. */
  [class*="colophon"] + p.meta, p.meta + [class*="colophon"],
  [class*="programme"] + p.meta, p.meta + [class*="programme"] {
    display: block !important;
    clear: both !important;
    margin-top: 0.5rem !important;
  }
}
```

### Post-Patch Assertions

| # | Assertion | Result |
|---|-----------|--------|
| 1 | `grep -c "hand-edit 2026-05-19"` returns 1 | ✅ PASS — exactly 1 at line 720 |
| 2 | `grep -c "hand-edit 2026-05-14"` returns 1 | ✅ PASS — exactly 1 at line 718 |
| 3 | File size delta positive and < 2KB | ✅ PASS — `git diff --stat` shows 22 insertions, 0 deletions |

---

## Phase 2 — Smoke (mobile-gate)

**Invocation:** `node /Users/andrepiresmacedo/andremacedo.com/scripts/mobile-gate.js /Users/andrepiresmacedo/andremacedo.com/index.html > /Users/andrepiresmacedo/andremacedo.com/state/mobile-gate-latest.json`

**Result:** `gate: "pass"`

### Full mobile-gate-latest.json

```json
{
  "gate": "pass",
  "checks": [
    {
      "name": "HORIZONTAL_OVERFLOW",
      "passed": true,
      "details": "No overflow detected"
    },
    {
      "name": "TEXT_OVERLAP",
      "passed": true,
      "details": "No significant text overlap detected"
    },
    {
      "name": "HEIGHT_RATIO",
      "passed": true,
      "details": "mobile=5219px desktop=12362px ratio=0.42"
    },
    {
      "name": "MASTHEAD_WHITESPACE",
      "passed": true,
      "details": "No whitespace issues"
    },
    {
      "name": "MOBILE_INTERACTIVITY",
      "passed": true,
      "details": "invariants installed, keyboard visible (8 keys), touch bridge works"
    }
  ],
  "summary": "All mobile checks passed"
}
```

---

## Phase 3 — Commit

**Status:** REACHED  
**Commit hash:** `56ff207`  
**Message:** `scaffold: viewport-containment for agent-generated sections — closes 9-cycle gen{N}-colophon revert loop`  
**Scope:** local only, no push

---

## Unexpected Conditions

- `knowledge-base/telos/raw/` directory (referenced in the decision memo path) does not exist in the project. The referenced decision memo file is not present. This result file was deposited to `telos/raw/` (created at project root) as the closest viable path matching the deposit contract.
- `~/andremacedo.com` resolved to `/Users/andrepiresmacedo/andremacedo.com` (not `/Users/andremacedo/andremacedo.com` as the tilde would naively expand — verified via glob match on the `.claude/` memory path).

---

## Files Read

- `/Users/andrepiresmacedo/andremacedo.com/index.html`
- `/Users/andrepiresmacedo/andremacedo.com/scripts/mobile-gate.js`
- `/Users/andrepiresmacedo/andremacedo.com/scripts/apply_changes.py` (lines 378-391, 1335-1351)
- `/Users/andrepiresmacedo/andremacedo.com/scripts/runner.sh` (mobile-gate invocation lines)
- `/Users/andrepiresmacedo/andremacedo.com/state/mobile-gate-latest.json`

## Files Modified

- `/Users/andrepiresmacedo/andremacedo.com/index.html` — 22 lines inserted into `<style id="mobile-scaffold">` block
- `/Users/andrepiresmacedo/andremacedo.com/state/mobile-gate-latest.json` — overwritten by gate runner with passing result
- `/Users/andrepiresmacedo/andremacedo.com/telos/raw/2026-05-19-result-andremacedo-creative-scaffold-fix.md` — this file (created)

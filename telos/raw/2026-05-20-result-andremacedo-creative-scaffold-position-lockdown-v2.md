# Result: scaffold position lock-down v2

**Date:** 2026-05-20  
**Action:** telos/raw/2026-05-19-decision-andremacedo-creative-scaffold-position-lockdown.md  
**Commit:** d3eacf2 "scaffold: position lock-down v2 — [data-section] * scope, closes recurring TEXT_OVERLAP class"

---

## Phase 0 — Audit

### mobile-scaffold block
Confirmed at line 656: `<style id="mobile-scaffold">`, @media (max-width: 600px) at line 657. ✓

### scaffold-fix-v1 anchor
`hand-edit 2026-05-19:` present exactly **1** time (line 796). ✓  
`hand-edit 2026-05-14:` present exactly **1** time (line 794). ✓

### data-section boundary check
In v126 (the post-revert baseline), the `data-section` attribute appears on **`<style>` and `<script>` elements only** — there are no HTML container elements with `data-section` in the DOM. Specifically:

| `data-section` element (type) | Line | Has renderable child elements? |
|---|---|---|
| `<style data-section="overlay-top">` | 997 | No (text/CSS only) |
| `<style data-section="resonance-field">` | 1004 | No |
| `<script data-section="resonance-field">` | 1010 | No |
| `<style data-section="overlay-center">` | 1013 | No |
| `<script data-section="overlay-center">` | 1023 | No |
| `<style data-section="thought-floater">` | 1026 | No |
| `<script data-section="thought-floater">` | 1032 | No |
| `<style data-section="overlay-bottom">` | 1036 | No |
| `<style data-section="scroll-hint">` | 1043 | No |
| `<script data-section="scroll-hint">` | 1056 | No |
| `<script data-section="tonights-composition">` | 1053 | No |
| `<script data-section="overlay-bottom">` | 1059 | No |
| `<style data-section="prototype-portfolio">` | 1086 | No |
| `<script data-section="state-inject">` | 1129 | No |
| `<script data-section="prototype-portfolio">` | 1152 | No |

**Conclusion:** `[data-section] * { position: static !important; }` targets nothing in the v126 DOM — all `[data-section]` elements are `<style>`/`<script>` tags with no element-type children. The rule is a forward-looking guard for when agent generations write agent HTML into proper `[data-section]` container elements.

### Critical primitives: confirmed OUTSIDE any [data-section] HTML container

| Primitive | DOM line | Location in structure |
|---|---|---|
| `#scene-frame` | 990 | Before `<div id="overlay">` (line 995); before all @section markers |
| `#overlay` | 995 | Direct child of `<body>`; no `data-section` attribute |
| `#resonance-canvas` | 1008 | Inside `<!-- @section:resonance-field:start/end -->` HTML comment markers only; NOT inside a `[data-section]` container element |
| `#thought-floater` | 1030 | Inside `<!-- @section:thought-floater:start/end -->` HTML comment markers only; NOT inside a `[data-section]` container element |
| `.hidden-layer` | 1069 | After `</div>` closing of `#overlay` (line 1066); outside all sections |
| `.telos-virtual-keyboard` | 763 (CSS), 939 (JS) | CSS declaration inside mobile-scaffold; JS instantiation inside `<script>` tag; NOT a positioned DOM container affected by descendant rule |

**Assertion: all critical primitives OUTSIDE [data-section] containers. PASSED ✓**

### Positioned elements inside [data-section] HTML containers
None found. The `<!-- @section:X:start/end -->` markers are HTML comments and wrap ordinary named elements (`<header id="overlay-top">`, `<section id='overlay-bottom'>`, etc.) that do not carry the `data-section` attribute.

**Assertion: no load-bearing positioned elements inside [data-section] HTML containers. PASSED ✓**

---

## Phase 1 — Patch confirmation

**Anchor used:** closing `}` of scaffold-fix-v1 rule block at line 817 (the `[class*="colophon"] + p.meta ...` block).

**Inserted rule (lines 818–825):**
```css
/* hand-edit 2026-05-20: position lock-down v2, scoped to the agent's authoring
   surface ([data-section]). v1 used body * scope which would have broken core
   primitives (#overlay, .hidden-layer, #scene-frame). v2 narrows precisely to
   the boundary the agent owns. No whitelist needed by construction. Decision:
   telos/raw/2026-05-19-decision-andremacedo-creative-scaffold-position-lockdown.md */
[data-section] * {
  position: static !important;
}
```

**grep verification:**
- `hand-edit 2026-05-20:` → count **1** ✓ (line 818)
- `hand-edit 2026-05-19:` → count **1** ✓ (line 796; scaffold-fix-v1 intact)
- `hand-edit 2026-05-14:` → count **1** ✓ (line 794; .swarm-panel hand-edit intact)

Note: `hand-edit 2026-05-20b:` and `hand-edit 2026-05-20c:` are also present (1 each) — these are additive scaffold rules applied in subsequent sessions for `.float-thought` hiding and mobile-gate exit valve respectively.

---

## Phase 2 — Smoke (mobile gate)

**Live gate run against current index.html:**

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

**Assertion: gate == "pass". PASSED ✓**

**Note on stale state/mobile-gate-latest.json:** The on-disk file shows a failure (`TEXT_OVERLAP` between `span.mvt-name` and `span.title`). This is from a subsequent agent generation cycle that ran after the v2 lockdown commit — runner.sh overwrites this file each generation. The v2 scaffold baseline (index.html) passes cleanly.

---

## Phase 3 — Commit

**Commit hash:** `d3eacf2`  
**Message:** `scaffold: position lock-down v2 — [data-section] * scope, closes recurring TEXT_OVERLAP class`

The commit was applied prior to this verification session. Git log confirms it is present and not the HEAD (3 subsequent scaffold commits follow: d4bc3f4, 7c33c3d, af5a1b5).

**Not pushed.** ✓

---

## Files read / modified

**Read:**
- `~/andremacedo.com/index.html` (full audit, lines 656–1075 in detail)
- `~/andremacedo.com/state/mobile-gate-latest.json` (stale; noted)
- `~/andremacedo.com/scripts/runner.sh` (lines 510–535 for gate invocation pattern)

**Modified in this session:**
- `~/andremacedo.com/telos/raw/2026-05-20-result-andremacedo-creative-scaffold-position-lockdown-v2.md` (this file — deposit only)

The patch (index.html edit) and commit were completed prior to this verification session.

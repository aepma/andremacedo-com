#!/usr/bin/env bash
# curate-references.sh — the taste layer's SELF-CURATION step. Runs SEPARATELY
# from the generation session (which has no web): a bounded, web-capable claude
# session studies current excellent design/design-engineering work and EVOLVES
# data/aesthetic-vocabulary.json — a grammar of transferable PRINCIPLES the
# generation prompt reads as creative material. Scheduled weekly / per-epoch.
#
# LAW it enforces on its own output:
#   - PRINCIPLES, never a catalog of sites/brands to imitate. No "copy X". No URLs
#     in principles. (mechanical guard below + prompt instruction.)
#   - Antifragile: the vocabulary may evolve but must never collapse toward one
#     look; it stays a grammar the 30% exploration floor fights WITH.
#   - FAIL-SAFE: a failed/empty/malformed/shrunken curation NEVER overwrites the
#     live vocabulary. The prior file persists; the chain degrades gracefully.
#
# Auth/billing: reuses ~/.telos/scripts/claude-subscription-exec.sh (OAuth
# preflight + env isolation + spend ceiling) — credentials are never handled here.
#
# Usage:   curate-references.sh              # live curation pass
#          curate-references.sh --self-test  # exercise validate+swap fail-safe, no LLM call
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VOCAB="$SITE_DIR/data/aesthetic-vocabulary.json"
HELPER="${ANDREMACEDO_HELPER:-$HOME/.telos/scripts/claude-subscription-exec.sh}"
log(){ echo "[curate-references $(date -u +%H:%M:%SZ)] $*" >&2; }

# ── validate a candidate vocabulary file: valid JSON, required structure,
#    principles-not-sites (no URLs in principles), and not drastically shrunken
#    vs the live file (anti-truncation). Returns 0 = acceptable, non-zero = reject.
validate_candidate() {
  local cand="$1" live="$2"
  [ -s "$cand" ] || { log "reject: candidate empty/missing"; return 1; }
  python3 - "$cand" "$live" <<'PY'
import json, sys
cand, live = sys.argv[1], sys.argv[2]
try:
    c = json.load(open(cand, encoding="utf-8"))
except Exception as e:
    print(f"reject: candidate not valid JSON ({e})", file=sys.stderr); sys.exit(1)
# required structure
for k in ("version", "contract", "principles", "generative_tensions"):
    if k not in c:
        print(f"reject: missing key {k!r}", file=sys.stderr); sys.exit(1)
prin = c.get("principles")
if not isinstance(prin, dict) or len(prin) < 4:
    print("reject: principles must be an object with >=4 categories", file=sys.stderr); sys.exit(1)
flat = []
for v in prin.values():
    if isinstance(v, list): flat += [str(x) for x in v]
if len(flat) < 12:
    print(f"reject: too few principles ({len(flat)} < 12)", file=sys.stderr); sys.exit(1)
# principles-not-sites guard: no raw URLs inside the principle strings
import re
for s in flat:
    if re.search(r"https?://", s):
        print("reject: a principle contains a URL (must be a grammar, not a site list)", file=sys.stderr); sys.exit(1)
# anti-truncation: candidate principle text must be >=60% of the live file's
try:
    lc = json.load(open(live, encoding="utf-8"))
    lflat = []
    for v in lc.get("principles", {}).values():
        if isinstance(v, list): lflat += [str(x) for x in v]
    live_chars = sum(len(x) for x in lflat) or 1
    cand_chars = sum(len(x) for x in flat)
    if cand_chars < 0.6 * live_chars:
        print(f"reject: candidate principle text shrank to {cand_chars}/{live_chars} (<60%)", file=sys.stderr); sys.exit(1)
except FileNotFoundError:
    pass  # no live file yet (first seed) — structure checks above suffice
sys.exit(0)
PY
}

# ── atomic swap with timestamped backup (only after validate passes) ──
swap_in() {
  local cand="$1"
  cp -p "$VOCAB" "$VOCAB.bak" 2>/dev/null || true
  mv "$cand" "$VOCAB"
  log "vocabulary updated (backup at data/aesthetic-vocabulary.json.bak)"
}

self_test() {
  log "SELF-TEST: validate+swap fail-safe"
  local tmp; tmp="$(mktemp -d)"; local rc=0
  local orig="$tmp/orig.json"; cp "$VOCAB" "$orig"
  # GOOD candidate: clone the live file (valid, same size) -> must ACCEPT
  cp "$VOCAB" "$tmp/good.json"
  if validate_candidate "$tmp/good.json" "$VOCAB"; then echo "PASS  good candidate ACCEPTED"; else echo "FAIL  good candidate rejected"; rc=1; fi
  # BAD: malformed JSON -> must REJECT
  echo '{ not json' > "$tmp/bad.json"
  if validate_candidate "$tmp/bad.json" "$VOCAB" 2>/dev/null; then echo "FAIL  malformed ACCEPTED"; rc=1; else echo "PASS  malformed JSON REJECTED"; fi
  # BAD: empty principles -> must REJECT
  echo '{"version":2,"contract":{},"principles":{},"generative_tensions":[]}' > "$tmp/empty.json"
  if validate_candidate "$tmp/empty.json" "$VOCAB" 2>/dev/null; then echo "FAIL  empty-principles ACCEPTED"; rc=1; else echo "PASS  empty principles REJECTED"; fi
  # BAD: URL in a principle -> must REJECT
  python3 - "$VOCAB" "$tmp/url.json" <<'PY'
import json,sys
c=json.load(open(sys.argv[1])); c["principles"]["typography"]=["copy https://example.com hero"]
json.dump(c,open(sys.argv[2],"w"))
PY
  if validate_candidate "$tmp/url.json" "$VOCAB" 2>/dev/null; then echo "FAIL  URL-in-principle ACCEPTED"; rc=1; else echo "PASS  URL-in-principle REJECTED (principles-not-sites)"; fi
  # BAD: drastically shrunken -> must REJECT
  python3 - "$VOCAB" "$tmp/tiny.json" <<'PY'
import json,sys
c=json.load(open(sys.argv[1]))
c["principles"]={"a":["x"],"b":["y"],"c":["z"],"d":["w"]}  # 4 cats but tiny text
json.dump(c,open(sys.argv[2],"w"))
PY
  if validate_candidate "$tmp/tiny.json" "$VOCAB" 2>/dev/null; then echo "FAIL  shrunken ACCEPTED"; rc=1; else echo "PASS  drastically-shrunken REJECTED (anti-truncation)"; fi
  # confirm live file untouched by the test
  if diff -q "$orig" "$VOCAB" >/dev/null; then echo "PASS  live vocabulary untouched by self-test"; else echo "FAIL  live vocabulary mutated!"; rc=1; fi
  rm -rf "$tmp"
  [ "$rc" -eq 0 ] && echo "SELF-TEST: OK" || echo "SELF-TEST: FAILED"
  return "$rc"
}

[ "${1:-}" = "--self-test" ] && { self_test; exit $?; }

# ───────────────────────── live curation pass ─────────────────────────
[ -x "$HELPER" ] || { log "FAIL-SAFE: helper $HELPER missing; keeping current vocabulary"; exit 2; }
[ -s "$VOCAB" ]  || { log "FAIL-SAFE: no current vocabulary at $VOCAB; refusing to create from a failable run"; exit 2; }

PROMPT_FILE="$(mktemp)"; OUTPUT_FILE="$(mktemp)"; CAND="$(mktemp).json"
trap 'rm -f "$PROMPT_FILE" "$OUTPUT_FILE" "$CAND"' EXIT
cat > "$PROMPT_FILE" <<EOF
You maintain the AESTHETIC VOCABULARY for andremacedo.com — a living generative
art organism that an AI rebuilds (dark, a persistent WebGL swarm, evolving epoch
identities). This vocabulary is creative material the generation agent reads; it
is NOT design law and NOT a style to enforce.

Your job this pass: study what is genuinely EXCELLENT and CURRENT in design and
design-engineering, then EVOLVE the vocabulary below — refine stale principles,
retire ones that are no longer distinctive, add transferable new ones the field
has surfaced. Use WebSearch/WebFetch for a FEW targeted queries (editorial/
computational/typographic web craft, what reads as crafted vs templated/AI-slop),
then synthesize. Do not over-research; depth of principle beats breadth of links.

HARD CONSTRAINTS (violating any makes your output unusable):
1. Output PRINCIPLES — a grammar of WHY a move reads as crafted — NEVER a catalog
   of specific sites, brands, or layouts to imitate. No "copy X". No URLs anywhere
   in the principles. Strip every proper noun and link from what you write.
2. Antifragile: the vocabulary may evolve but must NEVER collapse toward one look.
   Keep it a grammar the agent's exploration can fight WITH; if a principle can
   only be obeyed one way, rewrite it as a TENSION in generative_tensions.
3. Preserve the EXACT JSON schema of the current file: keys version (bump it),
   updated (today), maintained_by, contract (keep verbatim), principles (the same
   category structure, evolved), generative_tensions, provenance (replace with an
   ABSTRACT note of what you studied — no site list).
4. Keep it at least as rich as the current file; deepen, do not gut it.

Write the COMPLETE evolved JSON — and nothing else — to this exact path using the
Write tool: $CAND

===== CURRENT VOCABULARY =====
$(cat "$VOCAB")
===== END CURRENT VOCABULARY =====
EOF

log "running web-capable curation session (bounded)…"
# TELOS_AGENT is the helper's audit-log caller id. Unset, this pass lands in the
# shared executor log as the literal "unknown" and cannot be told apart from the
# generation runner's rows, which is the whole point of curating separately.
PROMPT_FILE="$PROMPT_FILE" OUTPUT_FILE="$OUTPUT_FILE" CLAUDE_MAX_BUDGET_USD="${CURATE_BUDGET_USD:-5.00}" \
  TELOS_AGENT="${TELOS_AGENT:-andremacedo-curate-references}" \
  bash "$HELPER" \
    --model "${CURATE_MODEL:-claude-opus-4-8}" \
    --allowedTools WebSearch WebFetch Read Write \
    --permission-mode bypassPermissions \
    --max-turns "${CURATE_MAX_TURNS:-24}" \
  || { log "FAIL-SAFE: curation session exited non-zero; keeping current vocabulary"; exit 1; }

if validate_candidate "$CAND" "$VOCAB"; then
  swap_in "$CAND"
  log "OK — vocabulary curated (version $(python3 -c 'import json;print(json.load(open("'"$VOCAB"'"))["version"])' 2>/dev/null || echo '?'))"
  exit 0
else
  log "FAIL-SAFE: candidate failed validation; keeping current vocabulary"
  exit 1
fi

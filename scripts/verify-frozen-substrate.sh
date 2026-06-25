#!/usr/bin/env bash
# verify-frozen-substrate.sh — durable assertion that scripts/frozen-substrate.html
# is (a) syntactically valid JS and (b) FENCE-SUFFICIENT: its blocks carry exactly
# the structural tokens validate-build.py requires for INV-5 (mobile scaffold +
# interaction) and INV-6 (swarm nervous system). Re-run after ANY edit to the
# frozen substrate. Exit 0 = all assertions hold; non-zero = a frozen guarantee
# was broken.
#
# This verifier is line-number-free on purpose: once Direction C lands, the frozen
# substrate is the source of truth, not index.html. Byte-identity to the original
# source is a one-time freeze-time proof (see the Phase 1a build report), not an
# ongoing contract.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SUB="$SITE_DIR/scripts/frozen-substrate.html"
fail=0
note(){ printf '  %s\n' "$*"; }
assert(){ # <desc> <test-cmd...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then printf 'PASS  %s\n' "$desc"
  else printf 'FAIL  %s\n' "$desc"; fail=1; fi
}
[ -s "$SUB" ] || { echo "FATAL: $SUB missing/empty"; exit 2; }

# (a) every inline <script> in the substrate parses under node --check
python3 - "$SUB" <<'PY' > /tmp/.fsub-scripts 2>/dev/null
import re,sys
html=open(sys.argv[1],encoding='utf-8').read()
html=re.sub(r'<!--.*?-->','',html,flags=re.S)   # ignore <script> mentions in comment prose
for i,m in enumerate(re.finditer(r'<script\b[^>]*>(.*?)</script>',html,re.S)):
    open(f'/tmp/.fsub-script-{i}.js','w',encoding='utf-8').write(m.group(1))
    print(f'/tmp/.fsub-script-{i}.js')
PY
nscripts=0
while IFS= read -r js; do
  nscripts=$((nscripts+1))
  assert "inline <script> #$nscripts parses (node --check)" node --check "$js"
done < /tmp/.fsub-scripts
note "(parsed $nscripts script block(s))"

# (b) fence-sufficiency: the structural tokens validate-build.py keys on
grep -q '<style id="mobile-scaffold">'                  "$SUB" && assert "INV-5 mobile-scaffold open tag present"      true || { assert "INV-5 mobile-scaffold open tag present" false; }
grep -Eq '@media[^{]*max-width[^{]*(600|[1-5][0-9][0-9])px' "$SUB" && assert "INV-5 mobile-scaffold @media max-width<=600" true || assert "INV-5 mobile-scaffold @media max-width<=600" false
grep -q '<script id="mobile-interaction-invariants">'   "$SUB" && assert "INV-5 mobile-interaction-invariants open tag present" true || assert "INV-5 mobile-interaction-invariants open tag present" false
for c in 'COMPONENT 1' 'COMPONENT 2' 'COMPONENT 3'; do
  grep -qF "$c" "$SUB" && assert "INV-5 $c marker present" true || assert "INV-5 $c marker present" false
done
grep -Eq '<[a-zA-Z]+[^>]*\bid="swarmPanel"' "$SUB" && assert "INV-6 #swarmPanel element present" true || assert "INV-6 #swarmPanel element present" false
# INV-6 also requires swarmPanel referenced from inline JS — must be inside a <script>, not just the element
python3 - "$SUB" <<'PY' && assert "INV-6 swarmPanel referenced from inline <script>" true || assert "INV-6 swarmPanel referenced from inline <script>" false
import re,sys
html=open(sys.argv[1],encoding='utf-8').read()
html=re.sub(r'<!--.*?-->','',html,flags=re.S)   # swarmPanel must be in a REAL script, not the comment
js=''.join(m.group(1) for m in re.finditer(r'<script\b[^>]*>(.*?)</script>',html,re.S))
sys.exit(0 if 'swarmPanel' in js else 1)
PY

echo ""
if [ "$fail" -eq 0 ]; then echo "verify-frozen-substrate: OK — substrate is valid JS and fence-sufficient (INV-5, INV-6)"; else echo "verify-frozen-substrate: FAILED — a frozen guarantee is broken"; fi
exit "$fail"

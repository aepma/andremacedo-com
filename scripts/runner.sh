#!/usr/bin/env bash
# runner.sh — andremacedo.com creative agent runner
# Usage: runner.sh --daily | --weekly | --event
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_FILE="$SITE_DIR/state/agent-state.json"
CHANGELOG="$SITE_DIR/state/changelog.md"
EXTERNAL_FILE="$SITE_DIR/data/external.json"
INDEX_FILE="$SITE_DIR/index.html"
SOUL_FILE="$SITE_DIR/SOUL.md"
# Direction C: the mutation engine is retired (regenerate-from-intent). Genome
# lineage bookkeeping moved to record-generation.py, run after the verdict gate.
RECORD_SCRIPT="$SCRIPT_DIR/record-generation.py"

LOG_FILE="$HOME/.telos/logs/andremacedo-agent.log"
mkdir -p "$(dirname "$LOG_FILE")"

# Wrangler runs non-interactively under launchd, which requires
# CLOUDFLARE_API_TOKEN — and neither deploy path ever exported it, so every
# scheduled daily run failed at the deploy step (2026-08-24/25). Read the
# Cloudflare vars from the TELOS env file when unset. Never print these values.
if [ -f "$HOME/.telos/.env" ]; then
  if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
    CLOUDFLARE_API_TOKEN=$(grep -E '^CLOUDFLARE_API_TOKEN=' "$HOME/.telos/.env" | head -1 | cut -d'=' -f2-)
    export CLOUDFLARE_API_TOKEN
  fi
  if [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
    CLOUDFLARE_ACCOUNT_ID=$(grep -E '^CLOUDFLARE_ACCOUNT_ID=' "$HOME/.telos/.env" | head -1 | cut -d'=' -f2-)
    export CLOUDFLARE_ACCOUNT_ID
  fi
fi

# Per-site logs and failure tracking (local to the site repo)
SITE_LOG_DIR="$SITE_DIR/logs"
ERROR_LOG="$SITE_LOG_DIR/build-errors.log"
BUILD_LOG="$SITE_LOG_DIR/build-$(date -u +%Y-%m-%d).log"
FAILURE_COUNTER="$SITE_DIR/state/build-failures.count"
# Threshold is cadence-coupled: the counter only advances once per scheduled
# run, so at the 1x/day daily cadence a threshold of 3 means three silent
# calendar days before the Telegram alert. 2 caps that at two days.
FAILURE_THRESHOLD=2
mkdir -p "$SITE_LOG_DIR"

# Portable timeout shim — macOS lacks GNU `timeout` by default.
# Mirrors pattern from ~/.telos/scripts/claude-auth-heartbeat.sh.
# Returns 124 on timeout to match GNU timeout exit-code convention used by callers.
if command -v gtimeout >/dev/null 2>&1; then
  _TMO_BIN="gtimeout"
elif command -v timeout >/dev/null 2>&1; then
  _TMO_BIN="timeout"
elif [ -x /opt/homebrew/bin/gtimeout ]; then
  _TMO_BIN="/opt/homebrew/bin/gtimeout"
else
  _TMO_BIN=""
fi
tmo() {
  local secs="$1"; shift
  if [ -n "$_TMO_BIN" ]; then
    "$_TMO_BIN" "$secs" "$@"
    return $?
  fi
  # Pure-bash fallback: background command + sleep watcher. SIGTERM on overrun.
  "$@" &
  local cmd_pid=$!
  ( sleep "$secs"; kill -TERM "$cmd_pid" 2>/dev/null ) &
  local watcher_pid=$!
  wait "$cmd_pid" 2>/dev/null
  local exit_code=$?
  kill -TERM "$watcher_pid" 2>/dev/null
  wait "$watcher_pid" 2>/dev/null
  # SIGTERM produces exit 143; report as 124 to match GNU timeout convention.
  if [ "$exit_code" -eq 143 ]; then return 124; fi
  return $exit_code
}


# launchd runs zsh -l -c which is non-interactive, so .zshrc is NOT sourced.
# Source it explicitly if ANTHROPIC_API_KEY is missing.
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -f "$HOME/.zshrc" ]; then
  set +eu  # .zshrc may have unbound refs or failing interactive-only commands
  # shellcheck disable=SC1091
  source "$HOME/.zshrc" 2>/dev/null || true
  set -eu
fi

BOT_TOKEN="${OPENCLAW_TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${OPENCLAW_TELEGRAM_CHAT_ID:-}"
PULSE_TYPE=""
case "${1:-}" in
  --daily)  PULSE_TYPE="daily" ;;
  --weekly) PULSE_TYPE="weekly" ;;
  --event)  PULSE_TYPE="event" ;;
  *)
    echo "Usage: $0 --daily | --weekly | --event" >&2
    exit 1
    ;;
esac

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"
}

# Agentic verification loop (2026-06-12): daily and weekly pulses run as a
# bounded multi-turn session that applies, validates, screenshots and inspects
# its own mutation before the runner deploys (SOUL.md perceptibility gate made
# honorable — the single-turn path could never see its own render). Event
# pulses keep the single-turn blind-shot path (f328732).
# Direction C: weekly + event REGENERATE (agentic regenerate-from-intent + full
# taste stack). daily is the cheap zero-LLM path (early branch below), never agentic.
AGENTIC=0
case "$PULSE_TYPE" in
  weekly|event) AGENTIC=1 ;;
esac

telegram() {
  if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then return 0; fi
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d chat_id="$CHAT_ID" -d parse_mode="Markdown" -d text="$1" >/dev/null 2>&1 || true
}

# Route build errors to the local error log. No Telegram noise on individual runs.
log_error() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$PULSE_TYPE] $*" >> "$ERROR_LOG"
  log "ERROR: $*"
}

# Consecutive-failure counter — launchd retries via the next scheduled run.
# After $FAILURE_THRESHOLD consecutive failures, send one Telegram and reset.
read_failure_count() {
  if [ -f "$FAILURE_COUNTER" ]; then cat "$FAILURE_COUNTER"; else echo 0; fi
}

record_failure() {
  DEPLOY_SUCCEEDED=1  # disarm EXIT trap — failure is already being recorded
  local count
  count=$(read_failure_count)
  count=$((count + 1))
  echo "$count" > "$FAILURE_COUNTER"
  if [ "$count" -ge "$FAILURE_THRESHOLD" ]; then
    telegram "andremacedo.com daily build failed ($count consecutive runs). Check $ERROR_LOG"
    echo 0 > "$FAILURE_COUNTER"
  fi
}

record_success() {
  echo 0 > "$FAILURE_COUNTER"
}

# Any exit path that doesn't reach record_success counts as a failure.
# Prevents silent skips (no deploy, no counter increment) from going undetected.
# One named function handles both cleanup and the guard so later trap calls
# (for temp-file cleanup) cannot silently overwrite the guard.
DEPLOY_SUCCEEDED=0

_on_exit() {
  # Cleanup temp files. Use ${VAR:+"$VAR"} so unset vars (early exits) produce
  # no argument rather than an empty-string argument to rm.
  rm -f \
    ${PROMPT_FILE:+"$PROMPT_FILE"} \
    ${HTTP_RESPONSE_FILE:+"$HTTP_RESPONSE_FILE"} \
    ${INPUT_JSONL_FILE:+"$INPUT_JSONL_FILE"} \
    ${HELPER_OUTPUT_FILE:+"$HELPER_OUTPUT_FILE"} \
    ${PARSE_RESULT_FILE:+"$PARSE_RESULT_FILE"} \
    2>/dev/null || true
  # Guard: any unexpected exit that didn't call record_failure must still trip
  # the counter so launchd's next run starts with an accurate failure count.
  if [ "${DEPLOY_SUCCEEDED:-0}" = "0" ]; then
    log_error "unexpected exit without deploy — tripping failure counter"
    record_failure
  fi
}
trap '_on_exit' EXIT

# `wrangler pages deploy` walks the WHOLE site directory and caps files at 25 MiB.
# It does not honour .gitignore or .wranglerignore for that walk. On 2026-08-31 an
# agentic pulse installed a Playwright browser cache inside the site dir
# (.pw-browsers, 149 MiB binary) and every deploy after it failed with
# "Pages only supports files up to 25 MiB" — visible only in wrangler's own log.
# Local tool caches are regenerable; the deploy is not optional. Purge them first.
purge_local_caches() {
  local cache
  for cache in .pw-browsers .pw-node .venv-pw; do
    if [ -e "$SITE_DIR/$cache" ]; then
      log "purging non-deployable local cache $cache from site dir before deploy"
      rm -rf "$SITE_DIR/$cache"
    fi
  done
}

# ── Direction C: DAILY is the cheap, zero-LLM path ─────────────────
# Refresh external data + sensorium, commit, deploy. The page's client-side
# time-of-day rotation provides the visible daily change. No claude session and
# no craft judge — a data refresh has no new design to judge, so judging it would
# burn budget for nothing. Weekly + event do the full agentic regenerate + taste
# stack. Skips the auth preflight and token ceiling on purpose (zero LLM spend).
if [ "$PULSE_TYPE" = "daily" ]; then
  log "daily cheap pulse (zero-LLM: refresh data + deploy)"
  bash "$SCRIPT_DIR/refresh.sh" >> "$LOG_FILE" 2>&1 || log "WARN: refresh.sh failed; deploying with prior data"
  cd "$SITE_DIR"
  git add -A
  git commit -m "agent: daily data refresh | pulse: daily" >> "$LOG_FILE" 2>&1 || log "daily: nothing to commit"
  purge_local_caches
  if ! npx wrangler pages deploy "$SITE_DIR" --project-name="andremacedo-com" --branch="main" --commit-dirty=true >> "$LOG_FILE" 2>&1; then
    log_error "daily wrangler deploy failed"
    record_failure
    exit 1
  fi
  tmo 30 git -C "$SITE_DIR" push origin HEAD 2>/dev/null || log "WARN: daily git push failed/timed out (non-fatal)"
  log "daily pulse complete (data refreshed + deployed; no LLM spend)"
  record_success
  DEPLOY_SUCCEEDED=1
  exit 0
fi

# ── Pre-flight (weekly + event only) ───────────────────────────────
if ! ~/.local/bin/claude auth status 2>/dev/null | python3 -c '
import json, sys
d = json.loads(sys.stdin.read())
sub_ok = (d.get("subscriptionType") == "max") or (d.get("authMethod") == "oauth_token")
sys.exit(0 if (sub_ok and d.get("loggedIn") is True and d.get("apiProvider") == "firstParty") else 1)
'; then
  log_error "subscription auth precondition failed"
  record_failure
  exit 1
fi

if [ ! -f "$STATE_FILE" ]; then
  log "ERROR: agent-state.json not found"
  exit 1
fi

# --- Monthly token counter auto-reset ---
# If state's last_token_reset_month differs from current YYYY-MM,
# zero monthly_tokens_used and update last_token_reset_month.
CURRENT_MONTH="$(date -u +%Y-%m)"
LAST_RESET_MONTH=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("last_token_reset_month",""))' < "$STATE_FILE")
if [ "$CURRENT_MONTH" != "$LAST_RESET_MONTH" ]; then
  log "Month rollover detected (${LAST_RESET_MONTH:-unset} -> $CURRENT_MONTH). Resetting token counter."
  python3 - "$STATE_FILE" "$CURRENT_MONTH" <<'PYEOF'
import json, sys
sf, cm = sys.argv[1], sys.argv[2]
with open(sf) as f:
    s = json.load(f)
s['monthly_tokens_used'] = 0
s['last_token_reset_month'] = cm
with open(sf, 'w') as f:
    json.dump(s, f, indent=2, ensure_ascii=False)
PYEOF
fi
# --- end auto-reset ---

MONTHLY_USED=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("monthly_tokens_used",0))' < "$STATE_FILE")
MONTHLY_CEILING=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("monthly_token_ceiling",200000))' < "$STATE_FILE")

if [ "$MONTHLY_USED" -ge "$MONTHLY_CEILING" ]; then
  log "Token ceiling reached ($MONTHLY_USED/$MONTHLY_CEILING). Skipping."
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$PULSE_TYPE] Token ceiling reached ($MONTHLY_USED/$MONTHLY_CEILING). Skipping." >> "$ERROR_LOG"
  DEPLOY_SUCCEEDED=1  # intentional skip — do not count as failure
  exit 0
fi

if [ "$PULSE_TYPE" = "event" ] && [ "$MONTHLY_USED" -ge $((MONTHLY_CEILING * 80 / 100)) ]; then
  log "Near ceiling. Skipping event pulse."
  DEPLOY_SUCCEEDED=1  # intentional skip — do not count as failure
  exit 0
fi

STATE="$(cat "$STATE_FILE")"
EXTERNAL="{}"
[ -f "$EXTERNAL_FILE" ] && EXTERNAL="$(cat "$EXTERNAL_FILE")"

TODAY="$(date -u +%Y-%m-%d)"
DAY_OF_WEEK="$(date -u +%A)"
HOUR="$(date -u +%H)"
if   [ "$HOUR" -ge 5  ] && [ "$HOUR" -lt 8  ]; then TOD="dawn"
elif [ "$HOUR" -ge 8  ] && [ "$HOUR" -lt 12 ]; then TOD="morning"
elif [ "$HOUR" -ge 12 ] && [ "$HOUR" -lt 17 ]; then TOD="afternoon"
elif [ "$HOUR" -ge 17 ] && [ "$HOUR" -lt 21 ]; then TOD="evening"
else TOD="night"
fi

# ── Capture screenshot of current site ────────────────────────────
SCREENSHOT="/tmp/andremacedo-current.jpg"
log "Capturing screenshot..."
if ! bash "$SCRIPT_DIR/screenshot.sh" >> "$LOG_FILE" 2>&1; then
  rm -f "$SCREENSHOT" /tmp/andremacedo-mobile.jpg
  # An agentic run opens its MANDATED SEQUENCE on the mobile sub-gate over the
  # ATTACHED live screenshots. With none attached the session cannot clear step 1;
  # it burns the full ~40min wall-clock, emits no result event, and reaches launchd
  # as a bare exit 1 with the real cause nowhere in the job's own report. That is
  # exactly how the 2026-08-24 Miami cutover (which left ~/.telos/playwright-venv
  # unbuilt, so screenshot.sh could not run) stayed invisible for three days across
  # two weekly runs. A fail-open capture must not feed a fail-closed gate: abort
  # before the session starts and name the cause. DAILY is AGENTIC=0 and has no
  # such gate, so it keeps the tolerant path.
  if [ "$AGENTIC" = "1" ]; then
    log_error "screenshot capture failed and this is an agentic run — the mobile sub-gate would have no live screenshots to read; aborting before the session starts (see $LOG_FILE for the capture error)"
    exit 1
  fi
  log "WARNING: Screenshot capture failed, continuing without visual context"
fi

# ── Build prompt ───────────────────────────────────────────────────
PROMPT_FILE="$(mktemp)"
HTTP_RESPONSE_FILE="$(mktemp)"

SCREENSHOT_ARG=""
[ -f "$SCREENSHOT" ] && SCREENSHOT_ARG="--screenshot=$SCREENSHOT"

python3 "$SCRIPT_DIR/build_prompt.py" "$PULSE_TYPE" "$STATE_FILE" "$EXTERNAL_FILE" "$INDEX_FILE" "$SOUL_FILE" "$CHANGELOG" "$TODAY" "$DAY_OF_WEEK" "$TOD" $SCREENSHOT_ARG > "$PROMPT_FILE"

# ── Dark TELOS activity feed: the missing consumer ─────────────────
# build_prompt.py writes the feed's health to state/ledger-staleness.json while
# building the section. Detection existed before and nothing read it, so a ledger
# that had not been written to since 2026-08-08 went unnoticed. One alert per day.
STALE_MSG="$(python3 - "$SITE_DIR/state/ledger-staleness.json" "$TODAY" <<'PYEOF' 2>/dev/null || true
import json, sys
path, today = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        m = json.load(f)
except Exception:
    sys.exit(0)
if not m.get("stale") or m.get("last_alert_date") == today:
    sys.exit(0)
if m.get("error"):
    print(f"TELOS activity feed unavailable to the andremacedo agent: {m['error']}. "
          "The epoch review is deciding without fleet evidence.")
else:
    age = m.get("age_hours") or 0
    print(f"TELOS activity ledger has been dark for {age/24:.1f} days (newest entry "
          f"{m.get('newest_entry')}). The andremacedo agent's fleet-awareness section is stale; "
          "the ledger's writers need a look.")
m["last_alert_date"] = today
with open(path, "w") as f:
    json.dump(m, f, indent=2, ensure_ascii=False)
PYEOF
)"
if [ -n "$STALE_MSG" ]; then
  log "$STALE_MSG"
  telegram "$STALE_MSG"
fi

# ── Agentic session protocol (appended last so it supersedes the
#    "Respond ONLY in valid JSON" reply contract above it) ─────────
if [ "$AGENTIC" = "1" ]; then
  # Stale artifacts from a previous run must never satisfy this run's gates.
  rm -f "$SITE_DIR/state/generation-meta.json"
  cat >> "$PROMPT_FILE" <<PROTOEOF


## AGENTIC SESSION PROTOCOL (supersedes any reply-format above)

You are a bounded agentic session with exactly these tools: Bash, Read, Write,
Edit. The repo is $SITE_DIR (absolute path; your cwd is already there). The
wall-clock backstop is ~40 minutes — budget is not your constraint, focus is.

You REGENERATE the site this run (Direction C): you write a COMPLETE,
self-contained index.html in place — resolving the HERO first, holding this
epoch's identity, using the appended aesthetic vocabulary as creative material.
This REPLACES the old mutation-diff flow entirely: do NOT write a mutation-diff
JSON and do NOT run the retired apply scripts — they no longer exist.

FROZEN SUBSTRATE (non-negotiable): scripts/frozen-substrate.html holds the
protected infrastructure (INV-5 mobile scaffold + interaction; INV-6 swarm panel,
its CSS, and driver). READ it first, then paste EVERY block from it into your
index.html VERBATIM at the right place — the <style> blocks in <head>/early body,
the swarm element in the body, the interaction + swarm-driver <script>s near the
end of <body>. Do not paraphrase, rename, or rewrite any frozen block, and do not
emit your own elements with the reserved ids/classes it lists. validate-build.py
REJECTS the page if any frozen block is missing or altered.

YOU OWN LEGIBILITY (INV-9): there is no auto-clamp anymore. Communicative text
MUST be WCAG-legible against its real rendered background, or the contrast gate
rejects the page (revert, no deploy). Decorative text may dissolve. Don't chase
hex math — judge legibility in your rendered screenshots (step 5).

TURN DISCIPLINE: the current index.html, state, and recent renders are ALREADY in
this prompt. Do NOT grep/sed the CSS line-by-line (the classic burnout). Explore
in 2-3 turns max, batching shell calls. Resolve the hero, regenerate, verify,
verdict — the moment every gate passes and the hero + self-introduction are
legible, emit OK and STOP. Polishing past a passing gate is how runs die.

MANDATED SEQUENCE — every step is an assertion gate; do not skip or reorder:

1. MOBILE SUB-GATE first on the attached live screenshots. If the current live
   page is mobile-broken in a way you must be careful not to reproduce, note it;
   your regenerated page is gated by mobile-gate.js below regardless. If you
   genuinely cannot proceed safely, end with exactly:
   GENERATION_VERDICT: SKIP — mobile_gate_fail: <issue>
2. READ scripts/frozen-substrate.html. Write your COMPLETE new index.html to
   $SITE_DIR/index.html with the Write tool — a full document (doctype through
   </html>), the frozen substrate pasted in VERBATIM, the hero resolved first,
   Andre's name visible, and the first-person self-introduction present and
   legible above the fold (INV-1/2/3).
3. Write your generation record to $SITE_DIR/state/generation-meta.json with the
   Write tool — raw JSON, the metadata schema specified above (fitness_evaluation,
   visual_strategy, accent_palette, palette_rationale, mood, kills, self_note,
   summary; plus epoch_name/obsession_update if the epoch changes; weekly also
   weekly_reflection). If the EPOCH REVIEW section is present in this prompt, the
   record MUST also carry epoch_review {verdict, reasoning} — a missing or
   malformed one rejects the generation, exactly like a failed gate, and nothing
   ships. This is your RECORD of the generation, NOT an apply-this-
   diff — your visual changes are already in the index.html you wrote.
4. Validate + render + run the DETERMINISTIC gates in ONE Bash call so each halts
   the chain (these are the SAME gates the runner re-runs after you — pass them here):
   python3 $SITE_DIR/scripts/validate-build.py $SITE_DIR/index.html && bash $SITE_DIR/scripts/screenshot-local.sh && node $SITE_DIR/scripts/mobile-gate.js $SITE_DIR/index.html && node $SITE_DIR/scripts/audit-contrast.js local $SITE_DIR/index.html
   ALL must succeed. validate-build.py enforces INVARIANTS.md statically (incl. the
   frozen substrate); screenshot-local.sh writes /tmp/andremacedo-self-desktop.jpg
   and -mobile.jpg; mobile-gate.js is the runtime MOBILE check — it names exact
   failures (e.g. \`TEXT_OVERLAP between "#a" and "#b"\`); audit-contrast.js rejects
   WCAG-illegible text (you own legibility, INV-9 — there is no auto-clamp). If ANY
   fails, read its output, make a TARGETED Edit to index.html fixing exactly what it
   names (do not eyeball mobile — fix the named elements), and re-run this whole chain.
5. LOOK at both screenshots with the Read tool (both in one turn). Apply the SOUL
   perceptibility gate + INVARIANTS to what you SEE:
   - Hero + first-person self-introduction fully visible above the fold and
     legible (INV-1/2). A dark void with no readable way in is a FAIL.
   - All communicative text readable against its real background (INV-9).
   - Mobile: no horizontal overflow, no clipped content, nothing occluding the
     viewport (INV-5 spirit).
   If any of these fail, make a targeted Edit to index.html, re-run the step-4
   validate+screenshot chain, and re-inspect. Stale screenshots prove nothing.

6. CRAFT GATE — the external critics decide, then you fix what they NAME. This is
   the loop that matters: your own taste just told you the page is fine, and the
   data says self-judgment is exactly the faculty that fails (gen-1 self-graded a
   centered-mandala SaaS page "OK"). So you do NOT grade your own craft — you RUN
   two independent critics and FIX their findings. On your render:
     python3 $SITE_DIR/scripts/craft-judge.py --desktop /tmp/andremacedo-self-desktop.jpg --json-out /tmp/craft-self.json --quiet ; echo "craft-exit=\$?"
   Read /tmp/craft-self.json. If "verdict" == "PASS", craft cleared — go to step 7.
   If "verdict" == "SLOP", the two critics each returned concrete findings
   (critics.A.findings, critics.B.findings) naming exactly what is generic, safe,
   or template-grade. Make TARGETED Edits to index.html that fix EACH named
   finding — do not argue, do not re-grade yourself, FIX what they named:
     • centered-symmetric hero  -> break the symmetry; one off-axis anchor
     • default purple/indigo/blue palette  -> a governed harmony, one dominant accent
     • undifferentiated card/circle grid  -> ONE element with real focal dominance
     • safe default sans everywhere  -> an intentional pairing (e.g. editorial serif + mono)
     • generic SaaS nav/hero/grid/footer shape  -> an editorial/zine composition
   Then re-run the FULL step-4 gate chain (validate + render + mobile + contrast —
   craft edits can break mobile layout/contrast) and re-run the craft judge.
   Repeat for AT MOST 3 craft iterations. Keep INV-9 legible throughout. Do NOT
   emit OK until the craft judge returns PASS. If still SLOP after 3 iterations,
   emit GENERATION_VERDICT: FAILED — craft: <the findings that persisted>.
   (The runner re-runs this SAME dual judge after you as the authoritative gate, so
   a real PASS is the only way to ship — there is no faking it.)

7. Final message: report concrete visual evidence (the hero and where it sits, the
   craft-judge verdict, how many craft iterations it took, what you fixed each
   round), then the verdict as the LAST line:
   - craft judge PASS + all gates clear:        GENERATION_VERDICT: OK
   - still SLOP/failing after the iterations:   GENERATION_VERDICT: FAILED — <what persisted>
   On FAILED/SKIP the runner keeps the previous deployment live and reverts your
   working tree. Never report OK without a fresh craft-judge PASS.

HARD RULES (violating any makes the generation FAILED):
- FOREGROUND ONLY. No trailing &, no nohup, no long sleeps, no servers —
  screenshot-local.sh owns its own server lifecycle. Nothing you started may
  still be running at your final message.
- Do NOT deploy (no wrangler, no deploy.sh) and do NOT git commit/push. The
  runner deploys only after your OK verdict and ITS gates: validate-build,
  mobile-gate.js, the contrast gate, and the DUAL adversarial craft judge.
- Do NOT modify SOUL.md, INVARIANTS.md, HEARTBEAT.md, MISSION.md, TOOLS.md,
  the chat widget, anything under scripts/ or launchd/, deploy.sh, or any file
  outside $SITE_DIR. You write index.html + state/generation-meta.json; fix
  iterations may Edit index.html and files under experiments/, assets/, data/.
PROTOEOF
fi

if [ "$PULSE_TYPE" = "weekly" ]; then MAX_TOKENS=16000
elif [ "$PULSE_TYPE" = "daily" ]; then MAX_TOKENS=16000
else MAX_TOKENS=10000
fi

# ── Call Claude via subscription helper ───────────────────────────
log "Starting $PULSE_TYPE pulse..."

# The agentic session's cwd is inherited from this process — make it the repo.
cd "$SITE_DIR"

INPUT_JSONL_FILE="$(mktemp)"
HELPER_OUTPUT_FILE="$(mktemp)"
PARSE_RESULT_FILE="$(mktemp)"

python3 - "$PROMPT_FILE" "${SCREENSHOT:-}" "$INPUT_JSONL_FILE" <<'PYEOF'
import base64, json, os, sys
prompt_file, screenshot, out_file = sys.argv[1], sys.argv[2], sys.argv[3]
with open(prompt_file) as f:
    prompt_text = f.read()
content = []
if screenshot and os.path.isfile(screenshot):
    with open(screenshot, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})
mobile_screenshot = "/tmp/andremacedo-mobile.jpg"
if os.path.isfile(mobile_screenshot):
    with open(mobile_screenshot, 'rb') as f:
        b64m = base64.b64encode(f.read()).decode('ascii')
    content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64m}})
content.append({"type": "text", "text": prompt_text})
with open(out_file, 'w') as f:
    f.write(json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + '\n')
PYEOF

# ANDREMACEDO_HELPER is a test seam (forced-failure dry runs); production
# default is the canonical subscription helper.
HELPER_SCRIPT="${ANDREMACEDO_HELPER:-$HOME/.telos/scripts/claude-subscription-exec.sh}"
# Hard wall on the whole claude session. No outer bounded-exec wraps this
# launchd job, so the runner owns the ceiling itself; tmo returns 124 on
# overrun, which lands in the helper-failure branch below (fail-closed).
# 2026-06-27 (Andre): doubled per-generation budget — wall 5400→10800s and dollar floor 50→100 so each generation gets 2x runway.
SESSION_WALL_CEILING=10800

set +e
if [ "$AGENTIC" = "1" ]; then
  # Bounded agentic session: tool allowlist is exactly file read/write/edit +
  # shell; stream-json + tail-aware failure logging kept (f328732).
  # Caps calibrated from the two 2026-06-12 smoke runs (both verified-good
  # work killed by single-turn-era caps): run 1 finished all gates + verdict
  # OK in 12 turns but died at $6.24 vs the $6 budget (error_max_budget_usd);
  # run 2 (budget 10) died at the 12-turn cap mid-fix-iteration at $8.43
  # (error_max_turns), ~$0.65/turn observed. 20 turns ≈ exploration + apply +
  # 2 fix iterations + verdict; 15.00 covers 20 turns with margin. The
  # SESSION_WALL_CEILING (2400s) stays as the outer runaway guard. Event
  # pulses keep the single-turn 6.00 path below.
  # UNCAPPED (Andre directive 2026-06-24): turn cap and dollar budget removed
  # — the last 3 daily builds (06-20/06-23/06-24) died at error_max_turns mid-
  # Edit, verified-good work killed by the 20-turn ceiling. The SESSION_WALL_
  # CEILING (2400s / 40min) is now the SOLE backstop: tmo returns 124 on overrun
  # → fail-closed helper-failure branch below. No turn or $ ceiling binds first.
  # NOTE: the helper (claude-subscription-exec.sh:44) defaults CLAUDE_MAX_BUDGET_USD
  # to $1.00 when UNSET and always forwards --max-budget-usd. Simply deleting the
  # env var (the 2026-06-24 first uncap attempt) therefore did NOT uncap — it
  # dropped the ceiling to $1 and killed the build in ~1 turn (44s). To make the
  # 40-min wall the sole binding backstop, we must SET a budget high enough that
  # the wall trips first: at ~$0.65/turn a 2400s session can't realistically
  # exceed ~$30, so 50.00 is effectively "uncapped relative to the wall."
  # TELOS_AGENT is the helper's audit-log caller id. Unset, every row this
  # runner writes lands as the literal "unknown" and the shared executor log
  # cannot be grouped by job. Pulse type is carried so the agentic build and
  # the single-turn pulse below stay distinguishable in the log.
  INPUT_JSONL="$INPUT_JSONL_FILE" OUTPUT_FILE="$HELPER_OUTPUT_FILE" CLAUDE_MAX_BUDGET_USD=100.00 \
    TELOS_AGENT="${TELOS_AGENT:-andremacedo-creative:${PULSE_TYPE:-runner.sh}}" \
    tmo "$SESSION_WALL_CEILING" bash "$HELPER_SCRIPT" \
    --model claude-opus-4-8 \
    --input-format stream-json --output-format stream-json \
    --verbose \
    --tools "Bash,Read,Write,Edit" \
    --permission-mode bypassPermissions \
    --strict-mcp-config --mcp-config "$HOME/.telos/andremacedo-runner-mcp.json" \
    --no-session-persistence
else
  # Event pulse keeps the single-turn blind-shot path (f328732).
  INPUT_JSONL="$INPUT_JSONL_FILE" OUTPUT_FILE="$HELPER_OUTPUT_FILE" CLAUDE_MAX_BUDGET_USD=12.00 \
    TELOS_AGENT="${TELOS_AGENT:-andremacedo-creative:${PULSE_TYPE:-runner.sh}}" \
    tmo "$SESSION_WALL_CEILING" bash "$HELPER_SCRIPT" \
    --model claude-opus-4-8 \
    --input-format stream-json --output-format stream-json \
    --max-turns 1 --verbose \
    --tools "" \
    --strict-mcp-config --mcp-config "$HOME/.telos/andremacedo-runner-mcp.json" \
    --no-session-persistence
fi
HELPER_EXIT=$?
set -e

# Persist the full stream-json transcript (perceptibility self-check evidence
# lives here); keep the last 14 so logs/ stays bounded.
SESSION_TRANSCRIPT="$SITE_LOG_DIR/session-$(date -u +%Y%m%dT%H%M%SZ)-$PULSE_TYPE.jsonl"
cp "$HELPER_OUTPUT_FILE" "$SESSION_TRANSCRIPT" 2>/dev/null || true
ls -t "$SITE_LOG_DIR"/session-*.jsonl 2>/dev/null | tail -n +15 | xargs rm -f 2>/dev/null || true

if [ "$HELPER_EXIT" != "0" ]; then
  {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$PULSE_TYPE] helper exit=$HELPER_EXIT"
    # The result/error event lives at the TAIL of the stream-json output; the
    # head is init boilerplate that fully consumes a fixed-size head snippet
    # (2026-06-11 blind-failure class). Extract the result event first, then
    # keep head+tail snippets for raw context.
    echo "--- result event (parsed) ---"
    python3 - "$HELPER_OUTPUT_FILE" <<'PYEOF' 2>&1 || true
import json, sys
last = None
for line in open(sys.argv[1], errors='replace'):
    line = line.strip()
    if not line:
        continue
    try:
        o = json.loads(line)
    except Exception:
        continue
    if isinstance(o, dict) and o.get('type') == 'result':
        last = o
if last is None:
    print('NO_RESULT_EVENT in helper output')
else:
    keys = ('subtype', 'is_error', 'num_turns', 'stop_reason', 'terminal_reason',
            'errors', 'total_cost_usd', 'duration_ms')
    print(json.dumps({k: last.get(k) for k in keys if k in last}))
    txt = (last.get('result') or '')
    if txt:
        print('result_text_head:', txt[:500])
PYEOF
    echo "--- head 2KB ---"
    head -c 2048 "$HELPER_OUTPUT_FILE" 2>/dev/null || true
    echo ""
    echo "--- tail 2KB ---"
    tail -c 2048 "$HELPER_OUTPUT_FILE" 2>/dev/null || true
    echo ""
  } >> "$ERROR_LOG"
  log "ERROR: helper exit=$HELPER_EXIT (details in $ERROR_LOG)"
  if [ "$AGENTIC" = "1" ]; then
    # The session died mid-flight (budget/turns/wall ceiling): the working
    # tree may hold a half-verified mutation that never reached the verdict
    # gate. Fail-closed — return index.html to the deployed state so the next
    # pulse starts clean (same policy as the verdict gate's FAILED branch).
    git -C "$SITE_DIR" checkout -- "$INDEX_FILE" 2>/dev/null || true
  fi
  record_failure
  exit 1
fi

python3 - "$HELPER_OUTPUT_FILE" "$PARSE_RESULT_FILE" <<'PYEOF'
import json, sys
out_path, result_path = sys.argv[1], sys.argv[2]
last = None
for line in open(out_path, errors='replace'):
    line = line.strip()
    if not line:
        continue
    try:
        o = json.loads(line)
    except Exception:
        continue
    if isinstance(o, dict) and o.get('type') == 'result':
        last = o
assert last, "NO_RESULT_EVENT"
assert not last.get('is_error'), f"IS_ERROR: {last}"
text = (last.get('result') or '').strip()
assert text, "EMPTY_RESULT"
u = last.get('usage') or {}
# Verdict is derived ONLY from the result event's .result field — never from
# the raw capture, which echoes the prompt (the 2026-06-10 verdict
# false-match lesson). Scan from the end; protocol puts it on the last line.
verdict = ''
for line in reversed([l.strip() for l in text.splitlines() if l.strip()]):
    if line.startswith('GENERATION_VERDICT:'):
        verdict = line
        break
with open(result_path, 'w') as f:
    json.dump({'text': text, 'usage': u, 'verdict': verdict}, f)
PYEOF

export CONTENT
if [ "$AGENTIC" = "1" ]; then
  CONTENT=""  # sourced from state/generation-meta.json after the verdict gate below
else
  CONTENT="$(python3 - "$PARSE_RESULT_FILE" <<'PYEOF'
import json, sys
print(json.load(open(sys.argv[1]))['text'])
PYEOF
)"
fi
INPUT_TOKENS="$(python3 - "$PARSE_RESULT_FILE" <<'PYEOF'
import json, sys
u = json.load(open(sys.argv[1]))['usage']
print((u.get('input_tokens') or 0) + (u.get('cache_creation_input_tokens') or 0))
PYEOF
)"
OUTPUT_TOKENS="$(python3 - "$PARSE_RESULT_FILE" <<'PYEOF'
import json, sys
print(json.load(open(sys.argv[1]))['usage'].get('output_tokens', 0))
PYEOF
)"
export TOTAL_TOKENS=$((INPUT_TOKENS + OUTPUT_TOKENS))

log "Tokens: $INPUT_TOKENS in + $OUTPUT_TOKENS out = $TOTAL_TOKENS"

# Write session entry for cost-report.sh auto-discovery
SESSIONS_DIR="$HOME/.telos/agents/andremacedo-creative/sessions"
mkdir -p "$SESSIONS_DIR"
SESSION_FILE="$SESSIONS_DIR/$(date -u +%Y-%m-%d).jsonl"
EPOCH_MS=$(python3 -c 'import time; print(int(time.time()*1000))')
python3 - "$EPOCH_MS" "$INPUT_TOKENS" "$OUTPUT_TOKENS" "$TOTAL_TOKENS" <<'PYEOF' >> "$SESSION_FILE"
import json, sys
entry = {
    'type': 'message',
    'message': {
        'role': 'assistant',
        'model': 'claude-opus-4-8',
        'timestamp': int(sys.argv[1]),
        'usage': {
            'input': int(sys.argv[2]),
            'output': int(sys.argv[3]),
            'cacheRead': 0,
            'cacheWrite': 0,
            'totalTokens': int(sys.argv[4])
        }
    }
}
print(json.dumps(entry))
PYEOF

# ── Verdict gate (agentic pulses) ─────────────────────────────────
# Token accounting above runs regardless of verdict — the session spent them.
if [ "$AGENTIC" = "1" ]; then
  # The session spent its tokens regardless of verdict, so the monthly-ceiling
  # accounting happens here with the real session usage.
  python3 - "$STATE_FILE" "$TOTAL_TOKENS" <<'PYEOF'
import json, sys
sf, tok = sys.argv[1], int(sys.argv[2])
with open(sf) as f:
    s = json.load(f)
s['monthly_tokens_used'] = s.get('monthly_tokens_used', 0) + tok
with open(sf, 'w') as f:
    json.dump(s, f, indent=2, ensure_ascii=False)
PYEOF

  VERDICT="$(python3 - "$PARSE_RESULT_FILE" <<'PYEOF'
import json, sys
print(json.load(open(sys.argv[1])).get('verdict', ''))
PYEOF
)"
  case "$VERDICT" in
    "GENERATION_VERDICT: OK"*)
      log "Session verdict: OK (self-verified against own render)"
      ;;
    "GENERATION_VERDICT: SKIP"*)
      # Healthy skip (e.g. mobile sub-gate on the live screenshots): no
      # mutation this cycle, previous deployment stays live, counter untouched.
      log "Session verdict: SKIP — $VERDICT"
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$PULSE_TYPE] session skip: $VERDICT" >> "$ERROR_LOG"
      git -C "$SITE_DIR" checkout -- "$INDEX_FILE" 2>/dev/null || true
      DEPLOY_SUCCEEDED=1
      exit 0
      ;;
    *)
      # FAILED or missing verdict: fail-closed. A generation that cannot
      # verify itself does not ship — previous deployment stays live.
      log_error "session verdict FAILED or missing ('${VERDICT:-<none>}') — no deploy, reverting working tree"
      {
        echo "--- session final message (first 3000 chars) ---"
        python3 - "$PARSE_RESULT_FILE" <<'PYEOF' 2>&1 || true
import json, sys
print(json.load(open(sys.argv[1])).get('text', '')[:3000])
PYEOF
        echo "--- transcript: $SESSION_TRANSCRIPT ---"
      } >> "$ERROR_LOG"
      git -C "$SITE_DIR" checkout -- "$INDEX_FILE" 2>/dev/null || true
      record_failure
      exit 1
      ;;
  esac

  # OK verdict requires this run's regenerated record (removed pre-session, so a
  # stale file cannot satisfy this). Fail-closed if the session lied.
  if [ ! -s "$SITE_DIR/state/generation-meta.json" ]; then
    log_error "verdict OK but state/generation-meta.json missing — fail-closed, no deploy"
    git -C "$SITE_DIR" checkout -- "$INDEX_FILE" 2>/dev/null || true
    record_failure
    exit 1
  fi
  if ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$SITE_DIR/state/generation-meta.json" 2>/dev/null; then
    log_error "verdict OK but generation-meta.json is not valid JSON — fail-closed, no deploy"
    git -C "$SITE_DIR" checkout -- "$INDEX_FILE" 2>/dev/null || true
    record_failure
    exit 1
  fi
  CONTENT="$(cat "$SITE_DIR/state/generation-meta.json")"
fi

# ── Record generation (genome lineage) ────────────────────────────
# Direction C: the session already wrote index.html directly. record-generation.py
# replaces the retired mutation engine's bookkeeping — reads generation-meta.json and updates
# genome.json + agent-state.json (generation++, fitness_log, color_history, epoch
# transitions, graveyard, mood, version stamp) and prints the one-line summary.
cd "$SITE_DIR"
export SITE_DIR PULSE_TYPE

APPLY_STDOUT="$(mktemp)"
if ! python3 "$RECORD_SCRIPT" "$SITE_DIR/state/generation-meta.json" "$PULSE_TYPE" "$SITE_DIR" >"$APPLY_STDOUT" 2>>"$ERROR_LOG"; then
  log_error "record-generation.py failed — fail-closed, no deploy. Reverting index.html."
  cat "$APPLY_STDOUT" >> "$ERROR_LOG"
  git -C "$SITE_DIR" checkout -- "$INDEX_FILE" 2>/dev/null || true
  rm -f "$APPLY_STDOUT"
  record_failure
  exit 1
fi

# Append this run's record output to the daily build log for diagnosis
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) [$PULSE_TYPE] record-generation output ==="
  cat "$APPLY_STDOUT"
  echo ""
} >> "$BUILD_LOG"

# ── Validate inline JS before commit/deploy ────────────────────────
# Gen 107 footgun: the agent emits minified IIFEs for new interactions and
# a single misplaced brace kills the entire main <script>. node --check via
# validate-build.py catches every inline <script> in index.html before
# runner commits/deploys. See:
# knowledge-base/personal/raw/2026-05-07-issue-runner-gene-injector-no-js-validation.md
if ! python3 "$SCRIPT_DIR/validate-build.py" "$INDEX_FILE" 2>>"$ERROR_LOG"; then
  log_error "JS validation failed — refusing to commit/deploy. Reverting index.html."
  # Don't ship a parse error to prod. Revert working tree on index.html so
  # the next launchd run starts clean. Genome.json may have advanced in
  # record-generation; that's a tolerable inconsistency the next successful
  # run absorbs.
  git -C "$SITE_DIR" checkout -- "$INDEX_FILE" 2>/dev/null || true
  if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
    telegram "andremacedo.com $PULSE_TYPE: JS validation failed — deploy aborted, working tree reverted. See $ERROR_LOG."
  fi
  record_failure
  exit 1
fi

# Count change types from the full output for the brief Telegram summary.
# awk is used (not grep -c) so that zero matches return "0" cleanly under set -e + pipefail.
CONTRAST_COUNT=$(awk '/contrast-gate/ {n++} END {print n+0}' "$APPLY_STDOUT")
SECTION_COUNT=$(awk '/replaced section|created section|deleted section|killed section/ {n++} END {print n+0}' "$APPLY_STDOUT")

SUMMARY="$(tail -n 1 "$APPLY_STDOUT")"
rm -f "$APPLY_STDOUT"

CURRENT_MOOD="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("current_mood","unknown"))' "$STATE_FILE")"
GENERATION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("generation",0))' "$SITE_DIR/state/genome.json")"

log "Applied: $SUMMARY"

# ── Epoch transition notice ───────────────────────────────────────
# When the backstop cleared the epoch, Andre sees that a machine made the call,
# not the agent. Authored metamorphoses are logged, not alerted.
EPOCH_MSG="$(python3 - "$SITE_DIR/state/epoch-transition-latest.json" "$GENERATION" <<'PYEOF' 2>/dev/null || true
import json, sys
try:
    with open(sys.argv[1]) as f:
        t = json.load(f)
except Exception:
    sys.exit(0)
if str(t.get("gen")) != str(sys.argv[2]):
    sys.exit(0)
if t.get("kind") != "mechanical":
    sys.exit(0)
print(f"andremacedo.com: epoch {t.get('epoch_number')} was cleared by the BACKSTOP, not by the "
      f"agent — {t.get('reason')}. The obsession is now empty; next weekly he authors the "
      "successor from the clearing.")
PYEOF
)"
if [ -n "$EPOCH_MSG" ]; then
  log "$EPOCH_MSG"
  telegram "$EPOCH_MSG"
fi

# ── Thought Stream: persist reasoning fragments ──────────────────
THOUGHT_STREAM_FILE="$SITE_DIR/state/thought-stream.json"

python3 - "$GENERATION" "$THOUGHT_STREAM_FILE" <<'PYEOF' 2>&1 | tee -a "$LOG_FILE" || log_error "thought-stream failed (non-fatal, deploy continues)"
import sys, json, os
from datetime import datetime, timezone

content_raw = os.environ['CONTENT']
content_str = content_raw.strip()
if content_str.startswith('```'):
    lines = content_str.split('\n')
    lines = lines[1:]
    if lines and lines[-1].strip() == '```':
        lines = lines[:-1]
    content_str = '\n'.join(lines)

data = json.loads(content_str)
gen = sys.argv[1]
stream_file = sys.argv[2]

self_note = data.get('self_note', '')
if isinstance(self_note, dict):
    self_note = str(self_note)
fitness = data.get('fitness_evaluation', {})
fitness_note = fitness.get('note', '') if isinstance(fitness, dict) else ''
weekly = data.get('weekly_reflection', '')

# Load existing stream or initialize
stream = []
if os.path.exists(stream_file):
    try:
        with open(stream_file) as f:
            stream = json.load(f)
    except (json.JSONDecodeError, IOError):
        stream = []

entry = {
    'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'generation': gen,
    'fragments': []
}

if self_note:
    entry['fragments'].append({'type': 'self_note', 'text': self_note})
if fitness_note:
    entry['fragments'].append({'type': 'fitness_note', 'text': fitness_note})
if weekly:
    entry['fragments'].append({'type': 'weekly_reflection', 'text': weekly})

if entry['fragments']:
    stream.append(entry)
    stream = stream[-100:]
    with open(stream_file, 'w') as f:
        json.dump(stream, f, indent=2)
    print(f'Thought stream: {len(entry["fragments"])} fragments for gen {gen}')
else:
    print('Thought stream: no fragments this pulse')
PYEOF

# ── Portfolio: rebuild manifest from genome data ─────────────────
python3 - "$SITE_DIR" <<'PYEOF' 2>&1 | tee -a "$LOG_FILE" || log_error "portfolio rebuild failed (non-fatal, deploy continues)"
import json, os, sys

site_dir = sys.argv[1]
genome_path = os.path.join(site_dir, 'state', 'genome.json')

with open(genome_path) as f:
    genome = json.load(f)

portfolio = {'epochs': []}

# Dead eras from graveyard
for entry in genome.get('graveyard', []):
    if entry.get('type') == 'era':
        portfolio['epochs'].append({
            'name': entry.get('name', 'unknown'),
            'status': 'archived',
            'generations': entry.get('generations', 0),
            'started': entry.get('started', ''),
            'ended': entry.get('died_date', ''),
            'epitaph': entry.get('epitaph', ''),
            'died_at_generation': entry.get('died_at_generation', 0),
            'artifacts': []
        })

# Current epoch
current_epoch = genome.get('epoch', 'unknown')
current_gen = genome.get('generation', 0)
epoch_started = genome.get('epoch_started', '')
portfolio['epochs'].append({
    'name': current_epoch,
    'status': 'active',
    'generations': current_gen,
    'started': epoch_started,
    'epitaph': None,
    'artifacts': []
})

# Attach dead artifacts to eras by generation range
for entry in genome.get('graveyard', []):
    if entry.get('type') == 'era':
        continue
    artifact = {
        'type': entry.get('type', 'unknown'),
        'name': entry.get('value', entry.get('name', 'unnamed')),
        'epitaph': entry.get('epitaph', ''),
        'died_at_generation': entry.get('died_gen', entry.get('died_at_generation', 0))
    }
    placed = False
    for epoch in portfolio['epochs']:
        if epoch['status'] == 'archived':
            max_gen = epoch.get('died_at_generation', 0)
            if artifact['died_at_generation'] <= max_gen:
                epoch['artifacts'].append(artifact)
                placed = True
                break
    if not placed and portfolio['epochs']:
        portfolio['epochs'][-1]['artifacts'].append(artifact)

portfolio['epochs'].reverse()
portfolio['fitness_trajectory'] = genome.get('fitness_log', [])[-20:]

portfolio_path = os.path.join(site_dir, 'state', 'portfolio.json')
with open(portfolio_path, 'w') as f:
    json.dump(portfolio, f, indent=2)
print(f'Portfolio: {len(portfolio["epochs"])} epochs')
PYEOF

# ── Mobile DOM gate — runs BEFORE commit/deploy ───────────────────
# Belt-and-suspenders: LLM gate in build_prompt.py catches obvious cases;
# this deterministic Playwright gate enforces hard structural invariants.
# On FAIL (exit 1): revert index.html, skip deploy, exit 0.
# Exit 0 (not 1) because gate firing is expected behavior, not a script error.
# DEPLOY_SUCCEEDED=1 disarms the EXIT trap so the failure counter does NOT
# trip on healthy gate firings — the agent retries with a fresh mutation next cycle.
GATE_OUT="$SITE_DIR/state/mobile-gate-latest.json"
set +e
node "$SCRIPT_DIR/mobile-gate.js" "$SITE_DIR/index.html" > "$GATE_OUT" 2>>"$ERROR_LOG"
GATE_EXIT=$?
set -e

if [ "$GATE_EXIT" = "1" ]; then
    log "Mobile gate FAIL - reverting index.html, skipping deploy this cycle"
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [gen $GENERATION] mobile-gate-fail: $(cat "$GATE_OUT" | head -1)" >> "$CHANGELOG"
    cat "$GATE_OUT" >> "$ERROR_LOG"
    cp "$SITE_DIR/index.html" "/tmp/last-failed-mobile-gate-$(date -u +%Y%m%dT%H%M%SZ).html" 2>/dev/null || true
    cd "$SITE_DIR" && git checkout HEAD -- index.html
    DEPLOY_SUCCEEDED=1
    exit 0
elif [ "$GATE_EXIT" = "2" ]; then
    log "Mobile gate ERROR (script issue, non-fatal) - proceeding with deploy"
    cat "$GATE_OUT" >> "$ERROR_LOG"
fi

# ── Pre-deploy contrast gate ───────────────────────────────────────
# Runs audit-contrast.js in local mode against the working-tree index.html. On
# CRITICAL failure: revert index.html, skip deploy this cycle (mirrors mobile-gate).
# Direction C: ALWAYS-ON for agentic regenerations — the old pre-deploy WCAG
# auto-clamp is gone, so this rejecting gate is now the contrast guarantee (the
# agent owns legibility; INV-9). Env override still forces it on elsewhere.
if [ "$AGENTIC" = "1" ] || [ "${CONTRAST_GATE_ENABLED:-0}" = "1" ]; then
    CONTRAST_GATE_OUT="$SITE_DIR/state/contrast-gate-latest.json"
    set +e
    tmo 30 node "$SCRIPT_DIR/audit-contrast.js" local "$SITE_DIR/index.html" > "$CONTRAST_GATE_OUT" 2>>"$ERROR_LOG"
    GATE_EXIT=$?
    set -e
    if [ "$GATE_EXIT" = "1" ]; then
        log "Contrast gate FAIL (CRITICAL) - reverting index.html, skipping deploy this cycle"
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [gen $GENERATION] contrast-gate-fail: $(jq -c '.summary.critical_failures' "$CONTRAST_GATE_OUT" 2>/dev/null || echo 'parse-error')" >> "$CHANGELOG"
        cat "$CONTRAST_GATE_OUT" >> "$ERROR_LOG"
        cd "$SITE_DIR" && git checkout HEAD -- index.html
        telegram "andremacedo.com $PULSE_TYPE: contrast gate CRITICAL failure on $(jq -r '.summary.critical_failures | length' "$CONTRAST_GATE_OUT" 2>/dev/null) elements — deploy skipped, working tree reverted."
        DEPLOY_SUCCEEDED=1
        exit 0
    elif [ "$GATE_EXIT" = "124" ]; then
        log "Contrast gate timed out (non-fatal, proceeding with deploy)"
    elif [ "$GATE_EXIT" != "0" ]; then
        log "Contrast gate ERROR (script issue, non-fatal, exit=$GATE_EXIT) - proceeding with deploy"
    fi
fi

# ── Taste gate: DUAL adversarial craft judge + coherence teeth ─────
# Direction C, fail-closed (same pattern as the contrast gate). Agentic
# regenerations only (daily already exited). is_slop from EITHER critic, a craft
# score below threshold, an unobtainable critic, OR abandoning the live epoch's
# identity => revert index.html, keep the previous deploy live, no ship.
if [ "$AGENTIC" = "1" ]; then
  # Fresh canonical render of the FINAL index.html for the critics to judge.
  if ! bash "$SCRIPT_DIR/screenshot-local.sh" >> "$LOG_FILE" 2>>"$ERROR_LOG"; then
    log_error "craft gate: screenshot-local.sh failed — fail-closed, no deploy"
    cd "$SITE_DIR" && git checkout HEAD -- index.html
    DEPLOY_SUCCEEDED=1
    exit 0
  fi
  CRAFT_OUT="$SITE_DIR/state/craft-judge-latest.json"
  set +e
  tmo 240 python3 "$SCRIPT_DIR/craft-judge.py" \
    --desktop /tmp/andremacedo-self-desktop.jpg \
    --mobile /tmp/andremacedo-self-mobile.jpg \
    --margin 7.3 \
    --json-out "$CRAFT_OUT" --quiet 2>>"$ERROR_LOG"
  CRAFT_EXIT=$?
  set -e

  # Persist the craft series (append-only), in BOTH outcomes. Until this existed
  # the two critics' scores lived only in the log line below: not persisted, not
  # fed back, not consumed — so the one signal that could end an epoch was
  # invisible to the agent. status=unobtainable when the judge could not produce
  # both critics (proxy 401 on 2026-07-26 and 2026-07-29), so an outage can never
  # be read as a flat score series and kill a healthy epoch.
  python3 "$SCRIPT_DIR/epoch_review.py" append-craft \
    --history "$SITE_DIR/state/craft-history.jsonl" \
    --craft-json "$CRAFT_OUT" \
    --gen "$GENERATION" \
    --judge-exit "$CRAFT_EXIT" >> "$BUILD_LOG" 2>>"$ERROR_LOG" \
    || log "WARN: craft-history append failed (non-fatal)"

  if [ "$CRAFT_EXIT" != "0" ]; then
    # 1 = slop / below threshold (either critic); 2 = a critic unobtainable; 124 = timeout.
    CRAFT_WHY="$(jq -r '.reason // .error // "craft gate failed"' "$CRAFT_OUT" 2>/dev/null || echo 'craft gate failed/timeout')"
    log_error "craft judge FAILED (exit $CRAFT_EXIT): $CRAFT_WHY — reverting index.html, no deploy"
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [gen $GENERATION] craft-fail: $CRAFT_WHY" >> "$CHANGELOG"
    cat "$CRAFT_OUT" >> "$ERROR_LOG" 2>/dev/null || true
    cd "$SITE_DIR" && git checkout HEAD -- index.html
    telegram "andremacedo.com $PULSE_TYPE: craft judge FAILED — ${CRAFT_WHY}. Deploy skipped, working tree reverted."
    DEPLOY_SUCCEEDED=1
    exit 0
  fi
  log "Craft judge PASSED: $(jq -r '"A="+(.critics.A.overall|tostring)+" B="+(.critics.B.overall|tostring)' "$CRAFT_OUT" 2>/dev/null || echo ok)"

  # Coherence teeth: the Coherence/Novelty axes are ENFORCED, not just logged.
  # Abandoning a live epoch's identity (no declared transition) = FAILED.
  set +e
  python3 - "$SITE_DIR/state/generation-meta.json" <<'PYEOF'
import json, sys
meta = json.load(open(sys.argv[1]))
fit = meta.get("fitness_evaluation", {}) or {}
coh = fit.get("coherence")
# A declared epoch transition (new epoch_name or a new obsession topic) is a
# sanctioned reinvention; coherence is only enforced when staying in-epoch.
transition = bool(meta.get("epoch_name")) or bool((meta.get("obsession_update") or {}).get("topic"))
if (not transition) and isinstance(coh, (int, float)) and coh < 4:
    print(f"coherence={coh} (<4) within a live epoch, no declared transition", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PYEOF
  COH_EXIT=$?
  set -e
  if [ "$COH_EXIT" != "0" ]; then
    log_error "coherence teeth FAILED — live epoch identity abandoned without a declared transition — reverting, no deploy"
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [gen $GENERATION] coherence-fail" >> "$CHANGELOG"
    cd "$SITE_DIR" && git checkout HEAD -- index.html
    telegram "andremacedo.com $PULSE_TYPE: coherence gate FAILED (live epoch abandoned). Deploy skipped, working tree reverted."
    DEPLOY_SUCCEEDED=1
    exit 0
  fi
fi

# ── Git commit (for history) ──────────────────────────────────────
git add -A
git commit -m "agent: ${SUMMARY} | mood: ${CURRENT_MOOD} | pulse: ${PULSE_TYPE}" || log "Nothing to commit"

# ── Archive: screenshot-only (git has full state history) ────────
TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
SCREENSHOT_DIR="$SITE_DIR/archive-screenshots"
SCREENSHOT_FILE="$SCREENSHOT_DIR/${TIMESTAMP}.png"
MANIFEST_FILE="$SCREENSHOT_DIR/manifest.json"

# Take screenshot of current live site
PLAYWRIGHT_PYTHON="$HOME/.telos/playwright-venv/bin/python3"
if [ -x "$PLAYWRIGHT_PYTHON" ]; then
  "$PLAYWRIGHT_PYTHON" - "$SCREENSHOT_FILE" <<'PYEOF' 2>/dev/null || echo "Archive screenshot failed (non-fatal)"
import asyncio, sys
from playwright.async_api import async_playwright
screenshot_file = sys.argv[1]
async def snap():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1200, 'height': 800})
        # 'domcontentloaded': networkidle/load never settle on the live site
        # (continuous animation + streaming resources); DCL fires in ~4s.
        await page.goto('https://andremacedo.com', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=screenshot_file, full_page=True)
        await browser.close()
asyncio.run(snap())
PYEOF
fi

# Append to manifest (git SHA, mood, fitness, timestamp)
GIT_SHA="$(git -C "$SITE_DIR" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
if [ -f "$SCREENSHOT_FILE" ]; then
  python3 - "$MANIFEST_FILE" "$TIMESTAMP" "$GIT_SHA" "$CURRENT_MOOD" "${FITNESS_SCORE:-0}" "${SUMMARY:-no summary}" <<'PYEOF' 2>/dev/null || echo "Manifest update failed (non-fatal)"
import json, sys
manifest_path = sys.argv[1]
timestamp = sys.argv[2]
git_sha = sys.argv[3]
mood = sys.argv[4]
try:
    fitness = json.loads(sys.argv[5]) if sys.argv[5] else 0
except Exception:
    fitness = 0
summary = sys.argv[6][:200]
try:
    with open(manifest_path) as f:
        manifest = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    manifest = []
manifest.append({
    'timestamp': timestamp,
    'screenshot': timestamp + '.png',
    'commit': git_sha,
    'mood': mood,
    'fitness': fitness,
    'summary': summary
})
with open(manifest_path, 'w') as f:
    json.dump(manifest, f, indent=2)
PYEOF
fi

# Prune old screenshots, keep last 100
cd "$SCREENSHOT_DIR" && ls -t *.png 2>/dev/null | tail -n +101 | xargs rm -f 2>/dev/null || true

# ── Deploy to Cloudflare Pages ────────────────────────────────────
# Phase-4 preview guard (Direction C build): when ANDREMACEDO_NO_PROD_DEPLOY=1 the
# generation + all gates + commit have already run on the current branch, but the
# prod deploy to main and the origin/main push are SKIPPED. Phase-4 previews come
# from the pushed engine-c branch (Cloudflare auto-previews non-prod branches),
# never from this prod path. Adds no non-main branch reference — INV-10 intact.
if [ "${ANDREMACEDO_NO_PROD_DEPLOY:-0}" = "1" ]; then
  log "NO_PROD_DEPLOY=1 — generation committed to $(git rev-parse --abbrev-ref HEAD 2>/dev/null); skipping prod deploy + origin/main push (preview build)."
  record_success
  DEPLOY_SUCCEEDED=1
  exit 0
fi

log "Deploying to Cloudflare Pages..."

export CLOUDFLARE_ACCOUNT_ID="98a1dcdbeec2aa3aac24e49c22c652d2"
purge_local_caches
if ! npx wrangler pages deploy "$SITE_DIR" --project-name="andremacedo-com" --branch="main" --commit-dirty=true 2>&1 | tee -a "$LOG_FILE" "$BUILD_LOG"; then
  log_error "wrangler deploy failed"
  record_failure
  exit 1
fi

log "Deployed to andremacedo.com"

# ── Push to GitHub (backup, non-blocking) ─────────────────────────
tmo 30 git -C "$SITE_DIR" push origin HEAD 2>/dev/null || log "WARN: git push failed or timed out (non-fatal)"

# Post-deploy contrast verification (CSS-declared, existing)
bash "$SCRIPT_DIR/contrast-check.sh" "$SITE_DIR" 2>/dev/null || echo "Contrast check failed (non-fatal)"

# ── Rendered-pixel contrast audit (new, soft gate) ────────────────
CONTRAST_AUDIT_OUTPUT="$SITE_DIR/state/contrast-audit-latest.json"
set +e
tmo 30 node "$SCRIPT_DIR/audit-contrast.js" "https://andremacedo.com" \
  > "$CONTRAST_AUDIT_OUTPUT" 2>>"$ERROR_LOG"
AUDIT_EXIT=$?
set -e

if [ "$AUDIT_EXIT" = "124" ]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [gen $GENERATION] audit-error: playwright timeout" >> "$CHANGELOG"
  log "Rendered-pixel audit timed out (non-fatal, skipping penalty)"
elif [ "$AUDIT_EXIT" != "0" ]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [gen $GENERATION] audit-error: script exited $AUDIT_EXIT" >> "$CHANGELOG"
  log "Rendered-pixel audit error exit=$AUDIT_EXIT (non-fatal, skipping penalty)"
else
  MISS_COUNT=$(python3 - "$CONTRAST_AUDIT_OUTPUT" <<'PYEOF'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    results = data.get('results') if isinstance(data, dict) else data
    print(sum(1 for r in results if isinstance(r, dict) and r.get('ratio', 99) < 4.5 and 'error' not in r))
except Exception:
    print(0)
PYEOF
)
  log "Rendered-pixel audit: $MISS_COUNT elements below 4.5:1"
  if [ "${MISS_COUNT:-0}" -gt 0 ]; then
    echo "[gen $GENERATION] CONTRAST MISS: $MISS_COUNT elements below 4.5:1" >> "$CHANGELOG"
    python3 - "$CONTRAST_AUDIT_OUTPUT" "$SITE_DIR/state/contrast-fail-gen-${GENERATION}.json" "$GENERATION" <<'PYEOF'
import json, sys
data = json.load(open(sys.argv[1]))
results = data.get('results') if isinstance(data, dict) else data
fails = [r for r in results if isinstance(r, dict) and r.get('ratio', 99) < 4.5 and 'error' not in r]
with open(sys.argv[2], 'w') as f:
    json.dump({'gen': int(sys.argv[3]), 'failures': fails}, f, indent=2)
PYEOF
    python3 - "$SITE_DIR/state/fitness-penalty.json" "$GENERATION" <<'PYEOF'
import json, sys
with open(sys.argv[1], 'w') as f:
    json.dump({'penalty': 1.5, 'reason': 'contrast', 'gen': int(sys.argv[2])}, f)
PYEOF
    log "Contrast penalty written: 1.5 for gen $GENERATION"
  fi
fi

# ── Notify ─────────────────────────────────────────────────────────
# Mark the run as successful: reset the consecutive-failure counter.
DEPLOY_SUCCEEDED=1
record_success

# Brief success message. Full technical output is in $BUILD_LOG.
FITNESS="$(python3 -c '
import json, sys
try:
    g = json.load(open(sys.argv[1]))
    log = g.get("fitness_log", [])
    if log:
        total = log[-1].get("total")
        print(total if total is not None else "n/a")
    else:
        print("n/a")
except Exception:
    print("n/a")
' "$SITE_DIR/state/genome.json")"

TG_MSG="andremacedo.com updated
Mood: ${CURRENT_MOOD} | Fitness: ${FITNESS}
${CONTRAST_COUNT} contrast fixes | ${SECTION_COUNT} section changes"

telegram "$TG_MSG"
log "$PULSE_TYPE complete. Tokens: $TOTAL_TOKENS. Contrast: $CONTRAST_COUNT, sections: $SECTION_COUNT, fitness: $FITNESS"

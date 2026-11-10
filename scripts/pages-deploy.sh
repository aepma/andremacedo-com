# pages-deploy.sh — the one Cloudflare Pages deploy step, sourced by runner.sh.
#
# Why one function: a connectivity blip to Cloudflare failed the daily pulse on
# 2026-09-24 ("fetch failed"), and the retry added then lived inside the daily
# branch only. The weekly pulse kept its own bare single attempt, so the same
# blip failed gen 264 on 2026-11-09T05:15Z and launchd held exit 1 until the
# next weekly slot (sentinel finding a5726a486b7f754d). A resilience rule that
# lives at one call site is a rule the next call site does not get, so every
# deploy now goes through this function.
#
# A Pages deploy of the same directory is idempotent, so network-class failures
# get a bounded retry with backoff. Anything else (file size, auth, config)
# fails at once so a real fault is not masked.
#
# Usage: pages_deploy LABEL [EXTRA_LOG...]
#   Deploys $SITE_DIR to production (branch main, per the deployment rules).
#   Output is appended to $LOG_FILE and to every EXTRA_LOG. On failure the
#   cause is recorded with log_command_failure and the exit code is returned;
#   the caller decides what failing means (record_failure, exit).
# Requires from the caller: SITE_DIR, LOG_FILE, log, log_command_failure.
# Tunables: PAGES_DEPLOY_ATTEMPTS (default 3), PAGES_DEPLOY_BACKOFF_S (default 60),
#   PAGES_DEPLOY_CMD (array, test seam; defaults to the wrangler command).

PAGES_DEPLOY_NETWORK_RE='fetch failed|connectivity issue|ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|socket hang up'

pages_deploy() {
  local label="$1"; shift
  [ -n "$label" ] || { echo "pages_deploy: label required" >&2; return 64; }
  [ -n "${SITE_DIR:-}" ] && [ -n "${LOG_FILE:-}" ] || { echo "pages_deploy: SITE_DIR and LOG_FILE required" >&2; return 64; }
  local attempts="${PAGES_DEPLOY_ATTEMPTS:-3}" backoff="${PAGES_DEPLOY_BACKOFF_S:-60}"
  local -a cmd
  if [ -n "${PAGES_DEPLOY_CMD+x}" ]; then
    cmd=("${PAGES_DEPLOY_CMD[@]}")
  else
    cmd=(npx wrangler pages deploy "$SITE_DIR" --project-name="andremacedo-com" --branch="main" --commit-dirty=true)
  fi
  local out attempt=1 rc=0 f
  out=$(mktemp "${TMPDIR:-/tmp}/andremacedo-deploy.XXXXXX") || return 70
  while :; do
    rc=0
    "${cmd[@]}" >"$out" 2>&1 || rc=$?
    cat "$out" >> "$LOG_FILE" 2>/dev/null || true
    for f in "$@"; do cat "$out" >> "$f" 2>/dev/null || true; done
    [ "$rc" -eq 0 ] && break
    [ "$attempt" -lt "$attempts" ] || break
    grep -qiE "$PAGES_DEPLOY_NETWORK_RE" "$out" || break
    log "WARN: $label deploy attempt $attempt/$attempts hit a network error; retrying in $((backoff * attempt))s"
    sleep $((backoff * attempt))
    attempt=$((attempt + 1))
  done
  if [ "$rc" -ne 0 ]; then
    log_command_failure "$label wrangler deploy failed (attempt $attempt/$attempts)" "$rc" "${cmd[*]}" "$out"
  fi
  rm -f "$out"
  return "$rc"
}

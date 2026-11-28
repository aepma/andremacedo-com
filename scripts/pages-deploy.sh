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
# Why a staged public folder (2026-11-28): this function used to hand wrangler
# the whole engine folder, and andremacedo.com served SOUL.md, scripts/runner.sh,
# state/, logs/ and references/ to anyone who asked. `wrangler pages deploy`
# reads none of .assetsignore, .cfignore or .wranglerignore (archive-screenshots/
# was on the ignore lists and was served), so a deny list in an ignore file
# protects nothing. The deploy now builds a fresh folder from an allowlist with
# pages_public_stage and publishes only that folder. A file is public only when
# it is on the allowlist or a public page links to it.
#
# A Pages deploy of the same directory is idempotent, so network-class failures
# get a bounded retry with backoff. Anything else (file size, auth, config)
# fails at once so a real fault is not masked.
#
# Usage: pages_deploy LABEL [EXTRA_LOG...]
#   Stages $SITE_DIR's public files and deploys them to production (branch
#   main, per the deployment rules). wrangler runs from the staged folder, so
#   the Pages Functions it builds (the site API) are the staged functions/
#   copy. Output is appended to $LOG_FILE and to every EXTRA_LOG. On failure the
#   cause is recorded with log_command_failure and the exit code is returned;
#   the caller decides what failing means (record_failure, exit).
# Requires from the caller: SITE_DIR, LOG_FILE, log, log_command_failure.
# Tunables: PAGES_DEPLOY_ATTEMPTS (default 3), PAGES_DEPLOY_BACKOFF_S (default 60),
#   PAGES_DEPLOY_CMD (array, test seam; defaults to the wrangler command; it runs
#   in the staged folder, which is also exported as PAGES_PUBLIC_DIR).

PAGES_DEPLOY_NETWORK_RE='fetch failed|connectivity issue|ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|socket hang up'

# Top-level files a visitor's browser asks for by name: the two pages, the chat
# widget, icons and logos, and the files Pages itself reads when present.
PAGES_PUBLIC_FILES='index.html archive.html chat-widget.js favicon.svg favicon.ico favicon-16x16.png favicon-32x32.png apple-touch-icon.png telos-logo.png telos-logo-sm.png site.webmanifest robots.txt sitemap.xml 404.html _headers _redirects _routes.json'
# Folders whose files are public only when a staged page, script or style links
# them: web pictures and full-size pictures the archive links, assets and
# experiment pages, and data files a page fetches at run time.
PAGES_PUBLIC_LINKED_RE='(assets|experiments|archive-screenshots|data)/[A-Za-z0-9._/-]*[A-Za-z0-9_-]'
# What may never be published, checked on the staged folder after it is built.
# A hit fails the deploy rather than publishing it.
PAGES_PRIVATE_RE='(^|/)\.|(^|/)(state|logs|scripts|references|outputs|launchd|worker|telos|memory|archive|node_modules|backups?)/|\.(md|sh|py|jsonl|log|toml|tar|gz|tgz|zip|bak)$|\.bak[.-]|(^|/)package(-lock)?\.json$'

# pages_public_stage SRC DEST: build DEST (absent or empty) holding only the
# public files of the site folder SRC. Exit 0 staged, 64 usage, 70 refused.
pages_public_stage() {
  local src="${1:-}" dest="${2:-}"
  [ -n "$src" ] && [ -n "$dest" ] || { echo "pages_public_stage: SRC and DEST required" >&2; return 64; }
  [ -d "$src" ] && [ -f "$src/index.html" ] || { echo "pages_public_stage: $src has no index.html" >&2; return 70; }
  if [ -e "$dest" ]; then
    [ -d "$dest" ] && [ -z "$(ls -A "$dest")" ] || { echo "pages_public_stage: $dest is not an empty folder" >&2; return 70; }
  else
    mkdir -p "$dest" || return 70
  fi
  src="$(cd "$src" && pwd -P)" || return 70
  dest="$(cd "$dest" && pwd -P)" || return 70
  case "$dest/" in "$src/"*) echo "pages_public_stage: DEST may not sit inside SRC" >&2; return 70 ;; esac

  local f rel new next round=0
  new="$dest/.stage-new"; next="$dest/.stage-next"
  : > "$new" || return 70
  for f in $PAGES_PUBLIC_FILES; do
    if [ -f "$src/$f" ] && [ ! -L "$src/$f" ]; then
      cp "$src/$f" "$dest/$f" || return 70
      echo "$f" >> "$new"
    fi
  done
  # The Pages functions folder (the site API), regular files only.
  if [ -d "$src/functions" ] && [ ! -L "$src/functions" ]; then
    while IFS= read -r rel; do
      rel="${rel#./}"
      case "$rel" in *..*|.*|*/.*) continue ;; esac
      mkdir -p "$dest/$(dirname "$rel")" && cp "$src/$rel" "$dest/$rel" || return 70
    done < <(cd "$src" && find functions -type f ! -name '.*')
  fi
  # Follow links from staged text files until nothing new is reached.
  while [ -s "$new" ]; do
    round=$((round + 1))
    [ "$round" -le 8 ] || { echo "pages_public_stage: links still growing after 8 rounds" >&2; return 70; }
    : > "$next"
    while IFS= read -r rel; do
      case "$rel" in *.html|*.htm|*.js|*.mjs|*.css|*.json|*.svg|*.webmanifest) ;; *) continue ;; esac
      case "$rel" in functions/*) continue ;; esac
      grep -ohE "$PAGES_PUBLIC_LINKED_RE" "$dest/$rel" 2>/dev/null || true
    done < "$new" | sort -u > "$next.refs"
    while IFS= read -r rel; do
      case "/$rel/" in */../*|*/./*|*//*) continue ;; esac
      for f in "$rel" "$rel.html" "$rel/index.html"; do
        if [ -f "$src/$f" ] && [ ! -L "$src/$f" ]; then
          if [ ! -e "$dest/$f" ]; then
            mkdir -p "$dest/$(dirname "$f")" && cp "$src/$f" "$dest/$f" || return 70
            echo "$f" >> "$next"
          fi
          break
        fi
      done
    done < "$next.refs"
    mv "$next" "$new" || return 70
  done
  rm -f "$new" "$next" "$next.refs"

  local bad
  bad=$(cd "$dest" && find . \( -type f -o -type l \) | sed 's|^\./||' | grep -E "$PAGES_PRIVATE_RE" | head -5) || bad=""
  if [ -n "$bad" ]; then
    echo "pages_public_stage: refusing to publish private files: $(echo "$bad" | tr '\n' ' ')" >&2
    return 70
  fi
  [ -f "$dest/index.html" ] || { echo "pages_public_stage: staged folder has no index.html" >&2; return 70; }
  return 0
}

pages_deploy() {
  local label="$1"; shift
  [ -n "$label" ] || { echo "pages_deploy: label required" >&2; return 64; }
  [ -n "${SITE_DIR:-}" ] && [ -n "${LOG_FILE:-}" ] || { echo "pages_deploy: SITE_DIR and LOG_FILE required" >&2; return 64; }
  local attempts="${PAGES_DEPLOY_ATTEMPTS:-3}" backoff="${PAGES_DEPLOY_BACKOFF_S:-60}"
  local stage rc=0
  stage=$(mktemp -d "${TMPDIR:-/tmp}/andremacedo-public.XXXXXX") || return 70
  pages_public_stage "$SITE_DIR" "$stage" >>"$LOG_FILE" 2>&1 || rc=$?
  if [ "$rc" -ne 0 ]; then
    log_error "$label deploy refused: the public folder could not be staged (exit $rc, see $LOG_FILE)"
    rm -rf "$stage"
    return "$rc"
  fi
  log "$label: staged $(cd "$stage" && find . -type f | wc -l | tr -d ' ') public files for deploy"
  local -a cmd
  if [ -n "${PAGES_DEPLOY_CMD+x}" ]; then
    cmd=("${PAGES_DEPLOY_CMD[@]}")
  else
    # The staged folder is no git repository, so pass the engine's commit, and
    # point wrangler at the engine's own cache (it holds the Pages account id the
    # daily run relies on) exactly as running from the engine folder did.
    local commit subject
    commit=$(git -C "$SITE_DIR" rev-parse HEAD 2>/dev/null) || commit=""
    subject=$(git -C "$SITE_DIR" log -1 --format=%s 2>/dev/null | cut -c1-300) || subject=""
    cmd=(npx wrangler pages deploy "$stage" --project-name="andremacedo-com" --branch="main" --commit-dirty=true)
    [ -n "$commit" ] && cmd+=(--commit-hash="$commit")
    [ -n "$subject" ] && cmd+=(--commit-message="$subject")
  fi
  local cache=""
  if [ -n "${WRANGLER_CACHE_DIR:-}" ]; then cache="$WRANGLER_CACHE_DIR"
  elif [ -d "$SITE_DIR/node_modules/.cache/wrangler" ]; then cache="$SITE_DIR/node_modules/.cache/wrangler"
  elif [ -d "$SITE_DIR/.wrangler/cache" ]; then cache="$SITE_DIR/.wrangler/cache"
  fi
  local out attempt=1 f
  out=$(mktemp "${TMPDIR:-/tmp}/andremacedo-deploy.XXXXXX") || { rm -rf "$stage"; return 70; }
  while :; do
    rc=0
    (
      cd "$stage" || exit 70
      export PAGES_PUBLIC_DIR="$stage"
      [ -n "$cache" ] && export WRANGLER_CACHE_DIR="$cache"
      "${cmd[@]}"
    ) >"$out" 2>&1 || rc=$?
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
  rm -rf "$stage"
  return "$rc"
}

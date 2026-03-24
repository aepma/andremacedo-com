# MISSION.md — Build & Deploy Instructions for Claude Code

Extract this archive and read SOUL.md, TOOLS.md, and HEARTBEAT.md before doing anything. They are the source of truth.

## What to build

### 1. GitHub repo + Cloudflare Pages
- Create repo for andremacedo.com, push all files, connect to Cloudflare Pages deploying from `main`
- Verify the seed site is live

### 2. Runner script
Calls Claude Opus 4.6 (`claude-opus-4-6`). Takes `--daily`, `--weekly`, or `--event` as argument.

Flow:
- Read `state/agent-state.json` + `data/external.json`
- Construct prompt from templates in HEARTBEAT.md
- Call the API, parse JSON response
- Apply changes to site files (thoughts.json, secrets.json, index.html CSS for weekly, agent-state.json, changelog.md)
- Commit and push to `main`
- Send Telegram notification (format in TOOLS.md)
- Track token usage in agent-state.json, enforce 200K monthly ceiling

Error handling: if API call fails, log error, Telegram alert, do NOT retry. Wait for next scheduled run.

### 3. Data refresh script (no LLM)
- Fetch gold spot price and Fort Lauderdale weather
- Write to `data/external.json` with timestamp
- Runs every 6 hours

### 4. Launchd jobs
- `com.openclaw.andremacedo.daily` — runner.sh --daily at 06:00 UTC daily
- `com.openclaw.andremacedo.weekly` — runner.sh --weekly at 04:00 UTC Sundays
- `com.openclaw.andremacedo.refresh` — refresh script every 6 hours

### 5. Telegram commands
Register in OpenClaw's Telegram interface:
- `/site status` — read agent-state.json, return mood, last update, obsession, tokens used
- `/site force-update` — trigger runner.sh --event immediately
- `/site redesign` — trigger runner.sh --weekly immediately
- `/site revert` — git revert HEAD and force-push
- `/site mood [value]` — write mood suggestion to agent-state.json for next run
- `/site obsession [topic]` — write obsession suggestion to agent-state.json for next run

## Constraints
- SOUL.md, TOOLS.md, HEARTBEAT.md are Tier 1 protected. Never modify them.
- No visitor tracking or analytics on the site
- Git commit format: `agent: [description] | mood: [current] | pulse: [daily|weekly|event]`
- If ambiguous, make a reasonable call, document in changelog.md, keep going.

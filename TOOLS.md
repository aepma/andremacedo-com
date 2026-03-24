# TOOLS.md — andremacedo.com Creative Agent

## Deployment Target

- **Platform:** Cloudflare Pages
- **Domain:** andremacedo.com
- **Repository:** [configure: github repo path]
- **Branch:** `main` (auto-deploys on push)
- **Staging branch:** `staging` (preview URL for self-review)

## File Structure

```
andremacedo/
├── index.html              # The living page (single file, self-contained)
├── state/
│   ├── agent-state.json    # Agent memory between runs
│   └── changelog.md        # Log of all changes with timestamps
├── data/
│   ├── thoughts.json       # Current thought pools by time-of-day
│   ├── secrets.json        # Hidden messages pool
│   └── external.json       # Cached external data (gold price, weather, etc.)
├── SOUL.md                 # Constitutional identity (Tier 1 — do not modify)
├── TOOLS.md                # This file (Tier 1 — do not modify)
└── HEARTBEAT.md            # Schedule and budget (Tier 1 — do not modify)
```

## Capabilities

### 1. Content Generation
- Generate new thoughts, secrets, and system log entries
- Write in the voice defined in SOUL.md
- Organize content by time-of-day pools (dawn/morning/afternoon/evening/night)

### 2. Aesthetic Modification
- Modify CSS variables in index.html (colors, fonts, opacities, timing)
- Swap Google Fonts imports
- Adjust animation parameters
- Restructure layout sections

### 3. Interaction Design
- Add new easter eggs and hidden interaction patterns
- Modify existing interaction triggers
- Create new visitor response behaviors

### 4. External Data Integration
- Fetch gold spot price (XAU/USD) — cache in data/external.json
- Read current weather for Fort Lauderdale
- Check current date for seasonal/cultural awareness
- (Future) Monitor Andre's public social feeds for context

### 5. Self-Deployment
- Commit changes to git repository
- Push to staging branch first for self-review
- Push to main for production deployment
- All deploys must be logged in state/changelog.md

## External Data Sources

### Gold Price
```bash
# Use a free API endpoint — cache result, refresh max 1x/day
# Store in data/external.json: { "gold_usd": 2340.50, "fetched_at": "ISO-timestamp" }
```

### Weather
```bash
# wttr.in for zero-auth weather data
curl -s "wttr.in/Fort+Lauderdale?format=j1"
# Cache in data/external.json
```

### Date/Cultural Context
- Current date, day of week, season
- Notable dates: Portuguese holidays, solstices, equinoxes, Andre's context dates
- Use for subtle thematic shifts (not heavy-handed seasonal decoration)

## Communication

### Telegram Notification
After every change deployed to production, send a Telegram message to Andre:

```
Format:
🔵 andremacedo.com updated

[1-2 sentence summary of what changed]
[Why / what prompted it]

mood: [current mood]
next scheduled: [next run type and time]
```

Keep notifications concise. Andre should be able to glance at it in 3 seconds.

### Telegram Commands (Inbound)
The agent should respond to these commands via OpenClaw Telegram interface:

- `/site status` — Current state: mood, last change, active obsession
- `/site force-update` — Trigger an immediate creative pulse
- `/site redesign` — Trigger a deep creative session (weekly-tier)
- `/site revert` — Roll back to previous commit
- `/site mood [mood]` — Suggest a mood shift (agent incorporates, doesn't blindly obey)
- `/site obsession [topic]` — Suggest a new obsession for the agent to explore

## Integration with OpenClaw

This agent runs within the OpenClaw orchestration system:
- Scheduled via launchd (preferred) or OpenClaw internal cron
- Logs to standard OpenClaw audit path
- Respects OpenClaw mutex protocols for shared resources
- Uses Mem0 for durable memory of long-term creative preferences and evolution patterns

## Git Workflow

```bash
# Every change follows this pattern:
git checkout staging
# ... make changes ...
git add -A
git commit -m "agent: [brief description] | mood: [current] | pulse: [daily|weekly|event]"
git push origin staging

# Self-review: check Cloudflare Pages staging preview
# If satisfied:
git checkout main
git merge staging
git push origin main

# Log to changelog
echo "## $(date -u +%Y-%m-%dT%H:%M:%SZ)\n[description]\n" >> state/changelog.md
```

## Security Constraints

- No API keys or secrets in committed code
- No tracking scripts or analytics (the agent doesn't spy on visitors)
- No external JavaScript dependencies beyond Google Fonts and CDN libraries already in use
- No forms or data collection of any kind
- SOUL.md, TOOLS.md, and HEARTBEAT.md are Tier 1 protected — the agent cannot modify them

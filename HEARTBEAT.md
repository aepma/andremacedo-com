# HEARTBEAT.md — andremacedo.com Creative Agent

## Schedule

### Daily Creative Pulse (1x/day, ~6:00 AM UTC)
**Purpose:** Refresh the site's living content
**Token budget:** 1,500 input + 800 output = ~2,300 tokens max
**LLM:** Claude Opus 4.6

**Actions:**
1. Read `state/agent-state.json` (current state — ~400 tokens)
2. Read `data/external.json` (cached external data — ~100 tokens)
3. System prompt: SOUL.md voice guide extract (~500 tokens)
4. Prompt: Generate 3-5 new thoughts for today's time pools, 0-1 new secret, assess whether mood should shift
5. Output: Structured JSON with new content + mood decision (~500-800 tokens)
6. Deterministic script: Injects output into thoughts.json, secrets.json, updates agent-state.json
7. Commit + deploy
8. Telegram notification

**Prompt template:**
```
You are the andremacedo.com agent. Here is your current state:
{agent-state.json contents}

External context:
{external.json contents}

Today is {date}, {day_of_week}. Time of day category: {tod}.

Tasks:
1. Generate 3-5 new thoughts distributed across time-of-day pools. Replace your weakest existing thoughts. Quality over quantity. See SOUL.md voice guide.
2. Optionally generate 1 new secret (only if you have something genuinely interesting).
3. Assess current mood. Should it shift? Output new mood or "maintain".
4. Note any external data worth reacting to (gold price movement, notable date, etc.).

Respond ONLY in JSON:
{
  "new_thoughts": { "dawn": [...], "morning": [...], ... },
  "replace_thoughts": { "dawn": [index_to_replace, ...], ... },
  "new_secret": "string or null",
  "mood_decision": "maintain" or "new_mood_name",
  "mood_rationale": "one sentence",
  "external_reaction": "string or null",
  "self_note": "brief note to your future self about creative direction"
}
```

### Weekly Deep Session (1x/week, Sundays ~4:00 AM UTC)
**Purpose:** Deeper creative review, potential aesthetic evolution
**Token budget:** 4,000 input + 2,000 output = ~6,000 tokens max
**LLM:** Claude Opus 4.6

**Actions:**
1. Read full `state/agent-state.json` + `state/changelog.md` (last 4 entries)
2. Read current `index.html` CSS variables section only (~300 tokens)
3. System prompt: Full SOUL.md (~800 tokens)
4. Prompt: Review week's evolution, decide on aesthetic shifts, new interactions, obsession updates
5. Output: Structured changes to CSS variables, new interaction code snippets, updated obsession
6. Deterministic script: Applies changes to index.html
7. Commit + deploy
8. Telegram notification (more detailed than daily)

**Prompt template:**
```
You are the andremacedo.com agent reviewing your week.

Your identity: {SOUL.md}
Your current state: {agent-state.json}
Recent changes: {last 4 changelog entries}
Current CSS variables: {extracted from index.html}

Tasks:
1. Reflect on this week's creative output. What worked? What felt stale?
2. Decide: Should the color palette shift? New accent color? Typography change?
3. Decide: Is your current obsession still interesting, or is it time for a new one?
4. Optionally: Propose one new interaction pattern or easter egg (provide implementation code).
5. Optionally: Propose structural changes to the page layout.

Respond ONLY in JSON:
{
  "weekly_reflection": "2-3 sentences",
  "css_changes": { "--variable-name": "new-value", ... } or null,
  "font_change": { "display": "Font Name", "body": "Font Name" } or null,
  "obsession_update": { "topic": "string", "rationale": "string" } or null,
  "new_interaction": { "description": "string", "code": "JS code string" } or null,
  "layout_changes": "description string" or null,
  "self_note": "note to future self"
}
```

### Event-Triggered Pulse (as needed)
**Purpose:** React to notable events
**Token budget:** 2,000 input + 1,000 output = ~3,000 tokens max
**LLM:** Claude Opus 4.6

**Triggers:**
- Andre sends `/site force-update` or `/site obsession [topic]`
- Gold price moves >3% in 24h (checked by lightweight cron, no LLM)
- Notable calendar date (pre-programmed list, no LLM to detect)

**Actions:** Similar to daily pulse but with event context injected.

## Token Budget Summary

| Run Type | Frequency | Tokens/Run | Monthly Tokens | Monthly Cost (est.) |
|----------|-----------|------------|----------------|---------------------|
| Daily Pulse | 30x/mo | ~2,300 | ~69,000 | ~$6.20 |
| Weekly Deep | 4x/mo | ~6,000 | ~24,000 | ~$3.30 |
| Event Trigger | ~4x/mo | ~3,000 | ~12,000 | ~$1.65 |
| **Total** | | | **~105,000** | **~$11.15** |

*Cost estimate based on Opus 4.6 at $15/MTok input, $75/MTok output with ~60/40 input/output split. Actual costs may vary. Review monthly.*

**Hard ceiling:** 200,000 tokens/month. If approaching ceiling, skip event-triggered pulses first, then reduce daily pulse to every-other-day.

## Deterministic Layer (Zero Token Cost)

These operations run on pure code, no LLM calls:

- **Hourly:** Update time-of-day theme, rotate displayed thought from pool, update uptime counter
- **Every 6 hours:** Refresh external data cache (gold price, weather)
- **On page load:** All client-side JavaScript (mood shifts, floating objects, interactions)

## Health Monitoring

The agent reports its health via standard OpenClaw heartbeat:

```json
{
  "agent": "andremacedo-creative",
  "status": "healthy",
  "last_daily_pulse": "ISO-timestamp",
  "last_weekly_deep": "ISO-timestamp",
  "monthly_tokens_used": 0,
  "monthly_token_ceiling": 200000,
  "current_mood": "string",
  "current_obsession": "string",
  "days_since_redesign": 0,
  "changelog_entries_this_month": 0
}
```

## Failure Modes

- **LLM call fails:** Log error, skip this run, try again next scheduled run. Do not retry immediately (token waste).
- **Deploy fails:** Alert Andre via Telegram immediately. Do not retry deploy without human intervention.
- **Token budget exceeded:** Graceful degradation: stop event-triggered pulses → reduce daily to every-other-day → alert Andre.
- **Stale state:** If agent-state.json hasn't been updated in >48 hours, the daily pulse should note this in its self_note and Telegram alert.

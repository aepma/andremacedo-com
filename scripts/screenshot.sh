#!/usr/bin/env bash
# screenshot.sh — Capture full-page screenshot at the page's actual rendered height.
# Output:
#   /tmp/andremacedo-current.png  (1200px wide, full rendered height up to 12000px ceiling)
#   ~/andremacedo.com/state/page-metrics.json  ({rendered_height_px, screenshot_height_px, timestamp})
set -euo pipefail

VENV="$HOME/.openclaw/playwright-venv/bin/python3"
OUT="/tmp/andremacedo-current.png"
RAW="/tmp/andremacedo-raw.png"
METRICS_FILE="$HOME/andremacedo.com/state/page-metrics.json"
HEIGHT_CEILING=12000

# Step 1: Capture full page at 1440px wide AND measure document.scrollHeight.
"$VENV" - << PYEOF
import asyncio, json, os
from datetime import datetime, timezone
from playwright.async_api import async_playwright

METRICS_FILE = os.path.expanduser("$METRICS_FILE")
RAW = "$RAW"

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("https://andremacedo.com", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        # Measure actual rendered page height BEFORE screenshot
        rendered_height = await page.evaluate("document.documentElement.scrollHeight")
        await page.screenshot(path=RAW, full_page=True)
        await browser.close()
        # Stash measured height for the bash side
        with open("/tmp/andremacedo-rendered-height", "w") as f:
            f.write(str(int(rendered_height)))
        # Pre-write metrics (screenshot_height_px filled in by bash after crop)
        os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
        existing = {}
        try:
            with open(METRICS_FILE) as f:
                existing = json.load(f)
        except Exception:
            existing = {}
        existing["rendered_height_px"] = int(rendered_height)
        existing["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(METRICS_FILE, "w") as f:
            json.dump(existing, f, indent=2)

asyncio.run(capture())
PYEOF

if [ ! -f "$RAW" ]; then
    echo "ERROR: Screenshot failed" >&2
    exit 1
fi

RENDERED_HEIGHT=$(cat /tmp/andremacedo-rendered-height 2>/dev/null || echo 0)
RAW_HEIGHT=$(sips -g pixelHeight "$RAW" 2>/dev/null | tail -1 | awk '{print $2}')
RAW_WIDTH=$(sips -g pixelWidth "$RAW" 2>/dev/null | tail -1 | awk '{print $2}')

# Step 2: If raw exceeds the safety ceiling, crop the bottom off (otherwise keep full).
if [ "${RAW_HEIGHT:-0}" -gt "$HEIGHT_CEILING" ]; then
    sips --cropOffset 0 0 --cropToHeightWidth "$HEIGHT_CEILING" "$RAW_WIDTH" "$RAW" --out "$OUT" >/dev/null 2>&1 || cp "$RAW" "$OUT"
else
    cp "$RAW" "$OUT"
fi

# Step 3: Scale width to 1200px (proportional height follows)
sips --resampleWidth 1200 "$OUT" --out "$OUT" >/dev/null 2>&1 || true

FINAL_HEIGHT=$(sips -g pixelHeight "$OUT" 2>/dev/null | tail -1 | awk '{print $2}')

# Step 4: Update metrics file with final screenshot height
"$VENV" - << PYEOF
import json, os
METRICS_FILE = os.path.expanduser("$METRICS_FILE")
final_h = int("${FINAL_HEIGHT:-0}")
try:
    with open(METRICS_FILE) as f:
        m = json.load(f)
except Exception:
    m = {}
m["screenshot_height_px"] = final_h
m["height_ceiling_px"] = $HEIGHT_CEILING
with open(METRICS_FILE, "w") as f:
    json.dump(m, f, indent=2)
PYEOF

rm -f "$RAW" /tmp/andremacedo-rendered-height
SIZE=$(stat -f%z "$OUT" 2>/dev/null || stat -c%s "$OUT" 2>/dev/null)
echo "Screenshot captured: $OUT (${SIZE} bytes)"
echo "  rendered_height=${RENDERED_HEIGHT}px  screenshot_height=${FINAL_HEIGHT}px  ceiling=${HEIGHT_CEILING}px"

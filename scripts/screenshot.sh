#!/usr/bin/env bash
# screenshot.sh — Capture full-page screenshot at the page's actual rendered height.
# Output:
#   /tmp/andremacedo-current.jpg  (1200px wide, full rendered height up to 12000px ceiling, JPEG q80)
#   ~/andremacedo.com/state/page-metrics.json  ({rendered_height_px, screenshot_height_px, timestamp})
set -euo pipefail

VENV="$HOME/.telos/playwright-venv/bin/python3"

# Remove stale outputs first: a failed capture must not leave yesterday's
# images behind for the runner to embed as today's visual context.
rm -f /tmp/andremacedo-current.jpg /tmp/andremacedo-mobile.jpg
OUT="/tmp/andremacedo-current.jpg"
RAW="/tmp/andremacedo-raw.png"
WORK="/tmp/andremacedo-current-work.png"
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
        # 'domcontentloaded', not 'networkidle'/'load': the live site animates,
        # polls, and holds streaming resources open, so neither settles within
        # 30s (timed out every run). DCL fires in ~4s; the 3s settle below
        # gives JS time to paint.
        await page.goto("https://andremacedo.com", wait_until="domcontentloaded", timeout=30000)
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

try:
    asyncio.run(capture())
except Exception as e:
    # One-line failure record; non-fatal upstream (runner continues without visual context).
    import sys
    print(f"screenshot capture failed: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else e}", file=sys.stderr)
    sys.exit(1)
PYEOF

if [ ! -f "$RAW" ]; then
    echo "ERROR: Screenshot failed" >&2
    exit 1
fi

RENDERED_HEIGHT=$(cat /tmp/andremacedo-rendered-height 2>/dev/null || echo 0)
RAW_HEIGHT=$(sips -g pixelHeight "$RAW" 2>/dev/null | tail -1 | awk '{print $2}')
RAW_WIDTH=$(sips -g pixelWidth "$RAW" 2>/dev/null | tail -1 | awk '{print $2}')

# Step 2: If raw exceeds the safety ceiling, crop the bottom off (otherwise keep full).
# Crop/resample run on a lossless PNG working file ($WORK); the final image is encoded JPEG q80 below.
if [ "${RAW_HEIGHT:-0}" -gt "$HEIGHT_CEILING" ]; then
    sips --cropOffset 0 0 --cropToHeightWidth "$HEIGHT_CEILING" "$RAW_WIDTH" "$RAW" --out "$WORK" >/dev/null 2>&1 || cp "$RAW" "$WORK"
else
    cp "$RAW" "$WORK"
fi

# Step 3: Scale width to 1200px (proportional height follows)
sips --resampleWidth 1200 "$WORK" --out "$WORK" >/dev/null 2>&1 || true

# Step 3b: API image size cap. Anthropic accepts ≤8000px on any side.
# If the scaled image exceeds 7500px tall, resample by height and let width shrink.
CUR_H=$(sips -g pixelHeight "$WORK" 2>/dev/null | tail -1 | awk '{print $2}')
if [ "${CUR_H:-0}" -gt 7500 ]; then
    sips --resampleHeight 7500 "$WORK" --out "$WORK" >/dev/null 2>&1 || true
fi

# Step 3c: Encode the resampled image as JPEG q80 (was lossless PNG — base64 PNG inflated the
# multimodal prompt ~8x; JPEG q80 is ample for the model to judge design). Final output is $OUT (.jpg).
sips -s format jpeg -s formatOptions 80 "$WORK" --out "$OUT" >/dev/null 2>&1 || cp "$WORK" "$OUT"

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

rm -f "$RAW" "$WORK" /tmp/andremacedo-rendered-height
SIZE=$(stat -f%z "$OUT" 2>/dev/null || stat -c%s "$OUT" 2>/dev/null)
echo "Screenshot captured: $OUT (${SIZE} bytes)"
echo "  rendered_height=${RENDERED_HEIGHT}px  screenshot_height=${FINAL_HEIGHT}px  ceiling=${HEIGHT_CEILING}px"

# ── Mobile capture (390x844, 2x device scale) ─────────────────────
MOBILE_OUT="/tmp/andremacedo-mobile.jpg"
MOBILE_RAW="/tmp/andremacedo-mobile-raw.png"
MOBILE_WORK="/tmp/andremacedo-mobile-work.png"
HEIGHT_CEILING_MOBILE=12000

"$VENV" - << PYEOF
import asyncio, json, os
from playwright.async_api import async_playwright

METRICS_FILE = os.path.expanduser("$METRICS_FILE")
MOBILE_RAW = "$MOBILE_RAW"

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
        )
        await page.goto("https://andremacedo.com", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        mobile_rendered_height = await page.evaluate("document.documentElement.scrollHeight")
        await page.screenshot(path=MOBILE_RAW, full_page=True)
        await browser.close()
        with open("/tmp/andremacedo-mobile-rendered-height", "w") as f:
            f.write(str(int(mobile_rendered_height)))
        existing = {}
        try:
            with open(METRICS_FILE) as f:
                existing = json.load(f)
        except Exception:
            existing = {}
        existing["mobile_rendered_height_px"] = int(mobile_rendered_height)
        with open(METRICS_FILE, "w") as f:
            json.dump(existing, f, indent=2)

try:
    asyncio.run(capture())
except Exception as e:
    # One-line failure record; non-fatal upstream (runner continues without visual context).
    import sys
    print(f"screenshot capture failed: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else e}", file=sys.stderr)
    sys.exit(1)
PYEOF

if [ ! -f "$MOBILE_RAW" ]; then
    echo "ERROR: Mobile screenshot failed" >&2
    exit 1
fi

MOBILE_RENDERED_HEIGHT=$(cat /tmp/andremacedo-mobile-rendered-height 2>/dev/null || echo 0)
MOBILE_RAW_HEIGHT=$(sips -g pixelHeight "$MOBILE_RAW" 2>/dev/null | tail -1 | awk '{print $2}')
MOBILE_RAW_WIDTH=$(sips -g pixelWidth "$MOBILE_RAW" 2>/dev/null | tail -1 | awk '{print $2}')

# Crop if raw exceeds safety ceiling
# Crop/resample run on a lossless PNG working file ($MOBILE_WORK); final image is encoded JPEG q80 below.
if [ "${MOBILE_RAW_HEIGHT:-0}" -gt "$HEIGHT_CEILING_MOBILE" ]; then
    sips --cropOffset 0 0 --cropToHeightWidth "$HEIGHT_CEILING_MOBILE" "$MOBILE_RAW_WIDTH" "$MOBILE_RAW" --out "$MOBILE_WORK" >/dev/null 2>&1 || cp "$MOBILE_RAW" "$MOBILE_WORK"
else
    cp "$MOBILE_RAW" "$MOBILE_WORK"
fi

# Scale width to 1200px (proportional height follows)
sips --resampleWidth 1200 "$MOBILE_WORK" --out "$MOBILE_WORK" >/dev/null 2>&1 || true

# Apply 7500px height ceiling
MOBILE_CUR_H=$(sips -g pixelHeight "$MOBILE_WORK" 2>/dev/null | tail -1 | awk '{print $2}')
if [ "${MOBILE_CUR_H:-0}" -gt 7500 ]; then
    sips --resampleHeight 7500 "$MOBILE_WORK" --out "$MOBILE_WORK" >/dev/null 2>&1 || true
fi

# Encode the resampled mobile image as JPEG q80 (was lossless PNG — see desktop note above).
sips -s format jpeg -s formatOptions 80 "$MOBILE_WORK" --out "$MOBILE_OUT" >/dev/null 2>&1 || cp "$MOBILE_WORK" "$MOBILE_OUT"

MOBILE_FINAL_HEIGHT=$(sips -g pixelHeight "$MOBILE_OUT" 2>/dev/null | tail -1 | awk '{print $2}')

# Update metrics with mobile screenshot height
"$VENV" - << PYEOF
import json, os
METRICS_FILE = os.path.expanduser("$METRICS_FILE")
mobile_final_h = int("${MOBILE_FINAL_HEIGHT:-0}")
try:
    with open(METRICS_FILE) as f:
        m = json.load(f)
except Exception:
    m = {}
m["mobile_screenshot_height_px"] = mobile_final_h
with open(METRICS_FILE, "w") as f:
    json.dump(m, f, indent=2)
PYEOF

rm -f "$MOBILE_RAW" "$MOBILE_WORK" /tmp/andremacedo-mobile-rendered-height
MOBILE_SIZE=$(stat -f%z "$MOBILE_OUT" 2>/dev/null || stat -c%s "$MOBILE_OUT" 2>/dev/null)
echo "Mobile screenshot captured: $MOBILE_OUT (${MOBILE_SIZE} bytes)"
echo "  mobile_rendered_height=${MOBILE_RENDERED_HEIGHT}px  mobile_screenshot_height=${MOBILE_FINAL_HEIGHT}px  ceiling=${HEIGHT_CEILING_MOBILE}px"

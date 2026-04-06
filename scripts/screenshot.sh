#!/usr/bin/env bash
# screenshot.sh — Capture full-page screenshot, crop to useful portion, resize
# Output: /tmp/andremacedo-current.png (1200px wide, top ~4200px of content)
set -euo pipefail

VENV="$HOME/.openclaw/playwright-venv/bin/python3"
OUT="/tmp/andremacedo-current.png"
RAW="/tmp/andremacedo-raw.png"

# Step 1: Capture full page at 1440px wide
"$VENV" - << 'PYEOF'
import asyncio
from playwright.async_api import async_playwright

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("https://andremacedo.com", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="/tmp/andremacedo-raw.png", full_page=True)
        await browser.close()

asyncio.run(capture())
PYEOF

if [ ! -f "$RAW" ]; then
    echo "ERROR: Screenshot failed" >&2
    exit 1
fi

# Step 2: Crop to top 5000px (hero + below-fold), then resize to 1200px wide
# sips --cropToHeightWidth crops from center, so we crop from top by:
# 1) Get raw height  2) If taller than 5000, crop off the bottom
HEIGHT=$(sips -g pixelHeight "$RAW" 2>/dev/null | tail -1 | awk '{print $2}')
WIDTH=$(sips -g pixelWidth "$RAW" 2>/dev/null | tail -1 | awk '{print $2}')

if [ "${HEIGHT:-0}" -gt 5000 ]; then
    # Crop bottom: pad top=0, left=0, bottom=(height-5000), right=0
    CROP_BOTTOM=$((HEIGHT - 5000))
    sips --cropOffset 0 0 --cropToHeightWidth 5000 "$WIDTH" "$RAW" --out "$OUT" >/dev/null 2>&1 || {
        # Fallback if cropOffset not supported: just use raw
        cp "$RAW" "$OUT"
    }
else
    cp "$RAW" "$OUT"
fi

# Step 3: Scale width to 1200px (proportional height follows)
sips --resampleWidth 1200 "$OUT" --out "$OUT" >/dev/null 2>&1 || true

rm -f "$RAW"
SIZE=$(stat -f%z "$OUT" 2>/dev/null || stat -c%s "$OUT" 2>/dev/null)
echo "Screenshot captured: $OUT (${SIZE} bytes)"

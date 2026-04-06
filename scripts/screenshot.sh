#!/usr/bin/env bash
# screenshot.sh — Capture headless screenshot of the live site
# Output: /tmp/andremacedo-current.png
set -euo pipefail

VENV="$HOME/.openclaw/playwright-venv/bin/python3"
OUT="/tmp/andremacedo-current.png"

"$VENV" - << 'PYEOF'
import asyncio
from playwright.async_api import async_playwright

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("https://andremacedo.com", wait_until="networkidle")
        await page.wait_for_timeout(3000)  # let particles render and swarm panel load
        await page.screenshot(path="/tmp/andremacedo-current.png", full_page=True)
        await browser.close()

asyncio.run(capture())
PYEOF

if [ -f "$OUT" ]; then
    SIZE=$(stat -f%z "$OUT" 2>/dev/null || stat -c%s "$OUT" 2>/dev/null)
    echo "Screenshot captured: $OUT (${SIZE} bytes)"
else
    echo "ERROR: Screenshot failed" >&2
    exit 1
fi

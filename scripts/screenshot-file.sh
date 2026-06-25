#!/usr/bin/env bash
# screenshot-file.sh — render a single self-contained HTML file to a model-readable
# JPEG (desktop viewport). Helper for craft-judge calibration fixtures and ad-hoc
# checks; the production loop uses screenshot-local.sh (which serves the site dir).
# Usage: screenshot-file.sh <html-file> <out.jpg>
set -euo pipefail
SRC="${1:?usage: screenshot-file.sh <html-file> <out.jpg>}"
OUT="${2:?usage: screenshot-file.sh <html-file> <out.jpg>}"
VENV="$HOME/.openclaw/playwright-venv/bin/python3"
RAW="${OUT%.jpg}-raw.png"
rm -f "$RAW" "$OUT"
ABS="$(cd "$(dirname "$SRC")" && pwd)/$(basename "$SRC")"

"$VENV" - "file://$ABS" "$RAW" <<'PYEOF'
import asyncio, sys
from playwright.async_api import async_playwright
url, raw = sys.argv[1], sys.argv[2]
async def cap():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1440, "height": 900})
        await pg.goto(url, wait_until="domcontentloaded", timeout=30000)
        await pg.wait_for_timeout(1200)
        await pg.screenshot(path=raw, full_page=True)
        await b.close()
asyncio.run(cap())
PYEOF

[ -f "$RAW" ] || { echo "ERROR: capture failed" >&2; exit 1; }
sips --resampleWidth 1200 "$RAW" --out "$RAW" >/dev/null 2>&1 || true
h=$(sips -g pixelHeight "$RAW" 2>/dev/null | tail -1 | awk '{print $2}')
[ "${h:-0}" -gt 7500 ] && sips --resampleHeight 7500 "$RAW" --out "$RAW" >/dev/null 2>&1 || true
sips -s format jpeg -s formatOptions 80 "$RAW" --out "$OUT" >/dev/null 2>&1 || cp "$RAW" "$OUT"
rm -f "$RAW"
[ -s "$OUT" ] || { echo "ERROR: output empty" >&2; exit 1; }
echo "wrote $OUT"

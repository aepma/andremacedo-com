#!/usr/bin/env bash
# screenshot-local.sh — render the WORKING TREE (not the live site) and capture
# desktop + mobile screenshots, so the creative session can inspect its own
# mutation BEFORE deploy (SOUL.md perceptibility gate, INVARIANTS INV-1/INV-9).
#
# Serves the site dir over a loopback HTTP server owned by the python process
# itself (in-process thread, port 0 = OS-assigned) so root-relative fetches
# like /state/agent-state.json resolve. No child processes are spawned and the
# server dies with the process — nothing is left running (headless rule).
#
# Output:
#   /tmp/andremacedo-self-desktop.jpg  (1440px viewport, full page, width 1200, JPEG q80)
#   /tmp/andremacedo-self-mobile.jpg   (390px viewport, 2x scale, width 1200, JPEG q80)
# Exit: 0 only if BOTH captures succeeded. Non-zero otherwise (fail-closed).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$HOME/.telos/playwright-venv/bin/python3"

DESKTOP_OUT="/tmp/andremacedo-self-desktop.jpg"
MOBILE_OUT="/tmp/andremacedo-self-mobile.jpg"
DESKTOP_RAW="/tmp/andremacedo-self-desktop-raw.png"
MOBILE_RAW="/tmp/andremacedo-self-mobile-raw.png"
HEIGHT_CEILING=12000

# Stale outputs must never pass as this run's evidence.
rm -f "$DESKTOP_OUT" "$MOBILE_OUT" "$DESKTOP_RAW" "$MOBILE_RAW"

"$VENV" - "$SITE_DIR" "$DESKTOP_RAW" "$MOBILE_RAW" <<'PYEOF'
import asyncio, functools, sys, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from playwright.async_api import async_playwright

site_dir, desktop_raw, mobile_raw = sys.argv[1], sys.argv[2], sys.argv[3]

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass

handler = functools.partial(QuietHandler, directory=site_dir)
server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
port = server.server_address[1]
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
url = f"http://127.0.0.1:{port}/index.html"

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # 'domcontentloaded', not 'load'/'networkidle': the page animates and
        # holds streaming resources open, so neither settles (same rationale
        # as screenshot.sh, commit 649c776). 3s settle lets JS paint.
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=desktop_raw, full_page=True)
        await page.close()

        page = await browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=2
        )
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=mobile_raw, full_page=True)
        await browser.close()

try:
    asyncio.run(capture())
finally:
    server.shutdown()
    server.server_close()
PYEOF

# Post-process to model-readable size (mirrors screenshot.sh: crop ceiling,
# width 1200, height <=7500 for the 8000px API cap, JPEG q80).
process_image() {
  local raw="$1" out="$2" work="${1%.png}-work.png"
  local raw_h raw_w cur_h
  raw_h=$(sips -g pixelHeight "$raw" 2>/dev/null | tail -1 | awk '{print $2}')
  raw_w=$(sips -g pixelWidth "$raw" 2>/dev/null | tail -1 | awk '{print $2}')
  if [ "${raw_h:-0}" -gt "$HEIGHT_CEILING" ]; then
    sips --cropOffset 0 0 --cropToHeightWidth "$HEIGHT_CEILING" "$raw_w" "$raw" --out "$work" >/dev/null 2>&1 || cp "$raw" "$work"
  else
    cp "$raw" "$work"
  fi
  sips --resampleWidth 1200 "$work" --out "$work" >/dev/null 2>&1 || true
  cur_h=$(sips -g pixelHeight "$work" 2>/dev/null | tail -1 | awk '{print $2}')
  if [ "${cur_h:-0}" -gt 7500 ]; then
    sips --resampleHeight 7500 "$work" --out "$work" >/dev/null 2>&1 || true
  fi
  sips -s format jpeg -s formatOptions 80 "$work" --out "$out" >/dev/null 2>&1 || cp "$work" "$out"
  rm -f "$work"
}

[ -f "$DESKTOP_RAW" ] || { echo "ERROR: desktop capture missing" >&2; exit 1; }
[ -f "$MOBILE_RAW" ]  || { echo "ERROR: mobile capture missing" >&2; exit 1; }
process_image "$DESKTOP_RAW" "$DESKTOP_OUT"
process_image "$MOBILE_RAW" "$MOBILE_OUT"
rm -f "$DESKTOP_RAW" "$MOBILE_RAW"

[ -s "$DESKTOP_OUT" ] || { echo "ERROR: desktop output empty" >&2; exit 1; }
[ -s "$MOBILE_OUT" ]  || { echo "ERROR: mobile output empty" >&2; exit 1; }
echo "Self-screenshots captured: $DESKTOP_OUT, $MOBILE_OUT"

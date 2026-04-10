#!/bin/bash
# Post-deploy contrast verification for andremacedo.com
# Reads built site HTML/CSS, extracts color pairs, computes WCAG ratios
# Outputs to state/contrast-report.json

set -euo pipefail
SITE_PATH="${1:-$HOME/andremacedo.com/assets}"
STATE_PATH="$HOME/andremacedo.com/state"
PY="$HOME/.openclaw/playwright-venv/bin/python3"

"$PY" - "$SITE_PATH" "$STATE_PATH" << 'PYEOF'
import json, re, sys, os
from datetime import datetime, timezone

site_path = sys.argv[1]
state_path = sys.argv[2]

def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c*2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def relative_luminance(rgb):
    vals = []
    for c in rgb:
        s = c / 255.0
        vals.append(s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]

def contrast_ratio(rgb1, rgb2):
    l1 = relative_luminance(rgb1)
    l2 = relative_luminance(rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)

color_pattern = re.compile(r"#[0-9a-fA-F]{3,8}\b")
colors_found = set()

for root, dirs, files in os.walk(site_path):
    for f in files:
        if f.endswith((".html", ".css", ".js")):
            try:
                with open(os.path.join(root, f)) as fh:
                    content = fh.read()
                    colors_found.update(color_pattern.findall(content))
            except Exception:
                pass

failures = []
colors = [c for c in colors_found if len(c.lstrip("#")) in (3, 6)]

for i, fg in enumerate(colors):
    for bg in colors[i+1:]:
        try:
            ratio = contrast_ratio(hex_to_rgb(fg), hex_to_rgb(bg))
            if ratio < 4.5 and ratio > 1.0:
                failures.append({"fg": fg, "bg": bg, "ratio": round(ratio, 2), "required": 4.5})
        except Exception:
            pass

report = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "total_colors": len(colors),
    "failures": sorted(failures, key=lambda x: x["ratio"])[:20],
    "pass": len(failures) == 0
}

os.makedirs(state_path, exist_ok=True)
out = os.path.join(state_path, "contrast-report.json")
with open(out, "w") as f:
    json.dump(report, f, indent=2)

print(json.dumps(report, indent=2))
PYEOF

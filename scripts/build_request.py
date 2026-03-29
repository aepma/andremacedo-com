#!/usr/bin/env python3
"""Build Anthropic API request JSON, optionally including a screenshot image."""
import json, sys, base64, os

prompt_file = sys.argv[1]
model = sys.argv[2]
max_tokens = int(sys.argv[3])
screenshot_path = sys.argv[4] if len(sys.argv) > 4 else ""

with open(prompt_file) as f:
    prompt_text = f.read()

content = []

# Include screenshot as image block if available
if screenshot_path and os.path.isfile(screenshot_path):
    with open(screenshot_path, "rb") as img:
        b64 = base64.b64encode(img.read()).decode("ascii")
    content.append({
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": b64,
        },
    })

content.append({"type": "text", "text": prompt_text})

request = {
    "model": model,
    "max_tokens": max_tokens,
    "messages": [{"role": "user", "content": content}],
}

print(json.dumps(request))

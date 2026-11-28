#!/usr/bin/env python3
"""Stub generator for test_orchestration.py. Stands in for one creative session.

Reads INPUT_JSONL, finds "CANDIDATE N OF M" (absent = the runner's single
attempt, slot "single"), and writes into the cwd:
  index.html                  the stub's source page plus a marker comment, with the
                              live page's knotted-string words removed (a fresh start
                              bans them); for a slot listed in STUB_FAIL_GATE an inline
                              script that does not parse is added, so validate-build.py
                              rejects it (INV-7; the swarm panel is optional since
                              2026-11-27)
  state/generation-meta.json  a record with its own idea and three recorded passes
  state/passes/pass-N/        one scene picture per recorded pass
and a Claude-shaped result event (GENERATION_VERDICT: OK) at OUTPUT_FILE.
It also records what it saw in STUB_TRACE (one JSON line per call).
"""
import json, os, re, sys

PASSES = 3

text = ""
with open(os.environ["INPUT_JSONL"], encoding="utf-8") as f:
    msg = json.loads(f.readline())
for p in msg["message"]["content"]:
    if p.get("type") == "text":
        text += p["text"]
m = re.search(r"CANDIDATE (\d+) OF (\d+)", text)
slot = m.group(1) if m else "single"
cwd = os.getcwd()

src = os.environ["STUB_SOURCE_INDEX"]
html = open(src, encoding="utf-8").read()
if slot in os.environ.get("STUB_FAIL_GATE", "").split(","):
    html = html.replace("</body>", "<script>function (</script>\n</body>", 1)
html = re.sub(r"khipu|quipu|knot", "piece", html, flags=re.I)
html = html.replace("</body>", f"<!-- stub candidate {slot} -->\n</body>", 1)
with open(os.path.join(cwd, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)
os.makedirs(os.path.join(cwd, "state"), exist_ok=True)
with open(os.path.join(cwd, "state", "generation-meta.json"), "w", encoding="utf-8") as f:
    json.dump({"obsession_update": {"topic": f"stub obsession {slot}", "rationale": "test"},
               "visual_strategy": f"stub strategy {slot}", "summary": f"stub summary {slot}",
               "idea": f"stub idea {slot}",
               "passes": [{"pass": n, "weakest_scene": f"scene {n}", "fix": "rebuilt it"}
                          for n in range(1, PASSES + 1)]}, f)
for n in range(1, PASSES + 1):
    d = os.path.join(cwd, "state", "passes", f"pass-{n}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "desktop-1.jpg"), "wb") as f:
        f.write(b"\xff\xd8\xff\xe0stub")

with open(os.environ["STUB_TRACE"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"slot": slot, "cwd": cwd, "cwd_in_prompt": cwd in text,
                        "site_in_prompt": os.environ["STUB_SITE"] + "/index.html" in text,
                        "saw_prior": "Earlier candidates in this run" in text,
                        "saw_references": "references/README.md" in text,
                        "saw_fresh": "FRESH START" in text,
                        "saw_form": "THE FORM (SOUL.md, The form)" in text,
                        "saw_images": any(p.get("type") == "image" for p in msg["message"]["content"]),
                        "saw_job": "within 10 seconds a stranger understands" in text}) + "\n")

event = {"type": "result", "subtype": "success", "is_error": False,
         "result": f"stub {slot} done\nGENERATION_VERDICT: OK",
         "usage": {"input_tokens": 100, "cache_creation_input_tokens": 0,
                   "cache_read_input_tokens": 0, "output_tokens": 10}}
with open(os.environ["OUTPUT_FILE"], "w", encoding="utf-8") as f:
    f.write(json.dumps(event) + "\n")
sys.exit(0)

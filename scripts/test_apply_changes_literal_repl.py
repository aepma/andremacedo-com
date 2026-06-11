#!/usr/bin/env python3
"""Regression test: model-generated replacement text must be treated as
LITERAL text by apply_changes.py, never as a re template.

2026-06-10 crash class: a section replacement containing a backslash
sequence (e.g. '\\u2014' inside generated JS) was passed to re.sub as a
template string, raising `re.error: bad escape \\u at position 408` and
killing the whole build.

Runs apply_changes.py end-to-end in a sandbox copy of the site with:
  1. a section replacement whose content contains \\u, \\d and \\g<0>
  2. a css_changes value containing a CSS escape (\\2014)
Expected: exit 0 and both strings land in index.html verbatim.
"""
import json, os, re, shutil, subprocess, sys, tempfile

SITE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPLY = os.path.join(SITE_DIR, "scripts", "apply_changes.py")

# Replacement payloads with every escape class that has bitten before
SECTION_JS_PAYLOAD = r"var s='— em dash'; var re2=/\d+/; var g='\g<0>';"
CSS_ESCAPE_VALUE = r"'\2014  literal-css-escape'"


def main():
    tmp = tempfile.mkdtemp(prefix="apply-changes-regress-")
    try:
        # Minimal site fixture: real index.html + state/ + data/
        shutil.copy(os.path.join(SITE_DIR, "index.html"), os.path.join(tmp, "index.html"))
        shutil.copytree(os.path.join(SITE_DIR, "state"), os.path.join(tmp, "state"))
        shutil.copytree(os.path.join(SITE_DIR, "data"), os.path.join(tmp, "data"))

        index_path = os.path.join(tmp, "index.html")
        with open(index_path) as f:
            html = f.read()

        # Pick a real section id from the fixture
        m = re.search(r"<!-- @section:([a-zA-Z0-9_-]+):start -->", html)
        assert m, "no @section markers found in index.html fixture"
        section_id = m.group(1)

        # Plant a CSS var for the css_changes leg
        html = html.replace("<style>", "<style>\n:root { --test-regress: old; }", 1)
        with open(index_path, "w") as f:
            f.write(html)

        content = {
            "section_operations": [{
                "action": "replace",
                "id": section_id,
                "content": f"<div>backslash test</div>\n<script>{SECTION_JS_PAYLOAD}</script>",
            }],
            "css_changes": {"--test-regress": CSS_ESCAPE_VALUE},
            "summary": "regression: literal-safe replacement",
        }

        env = dict(os.environ)
        env.update({
            "SITE_DIR": tmp,
            "PULSE_TYPE": "daily",
            "TOTAL_TOKENS": "0",
            "CONTENT": json.dumps(content),
        })
        proc = subprocess.run(
            [sys.executable, APPLY], env=env, cwd=tmp,
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            print("FAIL: apply_changes.py exited", proc.returncode)
            print("stdout:", proc.stdout[-2000:])
            print("stderr:", proc.stderr[-2000:])
            return 1

        with open(index_path) as f:
            out = f.read()
        for payload, label in ((SECTION_JS_PAYLOAD, "section JS payload"),
                               (CSS_ESCAPE_VALUE, "CSS escape value")):
            if payload not in out:
                print(f"FAIL: {label} not present verbatim in output index.html")
                return 1
        print(f"PASS: section '{section_id}' and css var replaced verbatim "
              "(backslash-u/-d/-g sequences intact, exit 0)")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

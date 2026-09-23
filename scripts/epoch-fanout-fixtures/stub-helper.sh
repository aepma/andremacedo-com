#!/usr/bin/env bash
# Stub ANDREMACEDO_HELPER for test_orchestration.py: no model call. Delegates to
# stub_generator.py, which writes a candidate into the cwd and a result event.
set -euo pipefail
exec python3 "$(cd "$(dirname "$0")" && pwd)/stub_generator.py"

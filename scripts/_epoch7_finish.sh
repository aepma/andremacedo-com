#!/usr/bin/env bash
# Idempotent finisher for ASSERTION 6 (commit) + ASSERTION 7 (render).
# Safe to run after _epoch7_commit.sh: if the reset commit already landed, it skips
# straight to the render. Logs everything; never auto-retries the render.
set -u
LOG=~/.openclaw/knowledge-base/telos/outputs/2026-05-31-epoch7-finish-run.log
REPO="$HOME/andremacedo.com"
MSG="andremacedo: soft reset to epoch 7 (clearing) — archived webgl-swarm, lineage preserved, agent self-seeds next obsession"
AUDIT="$HOME/.openclaw/logs/claude-subscription-exec.jsonl"
exec > >(tee "$LOG") 2>&1

echo "=== epoch7 finish run $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# tidy helper artifacts so they are not loose in the tree
rm -f "$REPO/scripts/_epoch7_reset.py" "$REPO/scripts/_epoch7_commit.sh"

# ---------- ASSERTION 6: ensure reset commit is present ----------
head_subj=$(git -C "$REPO" log -1 --pretty=%s)
reset_hash_before=""
if echo "$head_subj" | grep -q "soft reset to epoch 7"; then
  echo "ASSERTION6: reset commit already present -> $(git -C "$REPO" rev-parse --short HEAD): $head_subj"
  reset_hash_before=$(git -C "$REPO" rev-parse HEAD)
else
  echo "ASSERTION6: reset commit not found at HEAD; committing now."
  before=$(git -C "$REPO" rev-parse HEAD)
  ( cd "$REPO" && bash "$HOME/.openclaw/scripts/scoped-commit.sh" "$MSG" state/genome.json state/agent-state.json )
  echo "  helper rc=$?"
  if ! git -C "$REPO" log -1 --pretty=%s | grep -q "soft reset to epoch 7"; then
    echo "  helper did not land commit in andremacedo; fallback to direct scoped git commit"
    git -C "$REPO" add state/genome.json state/agent-state.json
    git -C "$REPO" commit -m "$MSG"
    echo "  fallback rc=$?"
  fi
  if git -C "$REPO" log -1 --pretty=%s | grep -q "soft reset to epoch 7"; then
    reset_hash_before=$(git -C "$REPO" rev-parse HEAD)
    echo "ASSERTION6 SUCCESS: $(git -C "$REPO" rev-parse --short HEAD)"
  else
    echo "ASSERTION6 FAILURE: could not create reset commit; NOT rendering."
    echo "=== STOP (commit failed) ==="
    exit 1
  fi
fi
echo "reset commit hash: $reset_hash_before"
echo "--- last 2 commits (pre-render) ---"
git -C "$REPO" log --oneline -2

# audit line count before render (to identify the new line afterwards)
audit_before=$( [ -f "$AUDIT" ] && wc -l < "$AUDIT" || echo 0 )
echo "audit lines before render: $audit_before"

# ---------- ASSERTION 7: render one daily generation ----------
echo "=== ASSERTION7: runner.sh --daily $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
start=$(date +%s)
bash "$REPO/scripts/runner.sh" --daily
run_rc=$?
end=$(date +%s)
wall=$((end - start))
echo "runner exit rc=$run_rc wall_sec=$wall"

echo "--- last 4 commits (post-render) ---"
git -C "$REPO" log --oneline -4
new_head=$(git -C "$REPO" rev-parse HEAD)
if [ "$new_head" != "$reset_hash_before" ]; then
  echo "NEW agent commit after reset: $(git -C "$REPO" log -1 --pretty='%h %s')"
else
  echo "No new commit after the reset commit (render may have failed before deploy)."
fi

echo "--- new audit line(s) since render ---"
if [ -f "$AUDIT" ]; then
  audit_after=$(wc -l < "$AUDIT")
  echo "audit lines after render: $audit_after"
  tail -n +"$((audit_before + 1))" "$AUDIT" | tail -3
fi

echo "=== finish run complete (run_rc=$run_rc wall=$wall) ==="
exit "$run_rc"

#!/usr/bin/env bash
# Chaos runner for BUG-2026-05-31-A: anti-regression loop authored but never
# committed, so CI ran nothing and the prevention prevented nothing.
#
# This is the meta-bug's own regression guard. The failure shape is NOT a
# pattern in a source file (a lint rule can't see it) — it's *absence*: the
# guard scripts + CI workflows existed only in the working tree, untracked, so
# GitHub Actions had no workflow to run. Detection = assert the loop is both
# committed (git-tracked) AND green (guards exit 0).
#
# If this runner fails, the repo has fallen back to the exact state that let
# the bug factory run unchecked: a feedback loop that isn't wired in.
set -uo pipefail

REPO="${KLIK_ONE_REPO:-/Users/wilsonxu/Klik_backup/Klik/Klik_one}"
fail=0

if [ ! -d "$REPO/.git" ]; then
  echo "SKIP: $REPO is not a git repo (set KLIK_ONE_REPO)"; exit 0
fi
cd "$REPO"

# 1. CI workflows must be git-TRACKED at the repo root (Actions only reads
#    .github/workflows at root; untracked = invisible to GitHub).
tracked_wf=$(git ls-files .github/workflows | grep -cE '\.ya?ml$')
if [ "$tracked_wf" -lt 1 ]; then
  echo "FAIL: no committed CI workflows at .github/workflows — CI runs nothing"; fail=1
else
  echo "✓ $tracked_wf CI workflow(s) committed at repo root"
fi

# 2. The guard scripts the workflows invoke must themselves be tracked.
for s in liquid/scripts/repo-guards.sh liquid/scripts/k1-guards.sh; do
  if git ls-files --error-unmatch "$s" >/dev/null 2>&1; then
    echo "✓ tracked: $s"
  else
    echo "FAIL: $s is not git-tracked — CI step would not find it"; fail=1
  fi
done

# 3. The guards must actually pass (hard rules clean) right now.
for s in liquid/scripts/repo-guards.sh liquid/scripts/k1-guards.sh; do
  if [ -f "$s" ]; then
    if bash "$s" >/dev/null 2>&1; then echo "✓ $s exits 0"; else echo "FAIL: $s hard rule violated"; fail=1; fi
  fi
done

echo "────────────────────────────────────────────"
if [ "$fail" -ne 0 ]; then echo "CHAOS FAILED — anti-regression loop is not wired in."; exit 1; fi
echo "CHAOS PASSED — loop committed + green."; exit 0

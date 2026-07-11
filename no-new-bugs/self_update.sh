#!/usr/bin/env bash
# Self-update this skill from its GitHub origin, run as Step 0 every time the
# skill is invoked (see SKILL.md). Updates only this skill's subtree from the
# default branch. Unrelated repository dirt and feature branches must not freeze
# a globally installed skill; genuine edits inside this skill still block the
# update so they are never overwritten.
#
# Fail-soft on every external failure (offline, not a git checkout): the skill
# must still run from the local copy when GitHub is unreachable. Exit is always 0
# so a self-update never blocks the skill.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_raw="$(git -C "$here" rev-parse --show-toplevel 2>/dev/null)" || {
  echo "skill self-update: not a git checkout — using local copy"; exit 0; }
repo="$(cd "$repo_raw" && pwd -P)"
skill_path="${here#"$repo"/}"

# Resolve the default branch from origin/HEAD; fall back to main.
def="$(git -C "$repo" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@')"
def="${def:-main}"

git -C "$repo" fetch --quiet origin "$def" 2>/dev/null || {
  echo "skill self-update: network unavailable or origin unreachable — using local copy"; exit 0; }

if git -C "$repo" diff --quiet "origin/$def" -- "$skill_path" 2>/dev/null; then
  echo "skill self-update: up to date"
  exit 0
fi

if ! git -C "$repo" diff --quiet HEAD -- "$skill_path" 2>/dev/null \
  || [ -n "$(git -C "$repo" ls-files --others --exclude-standard -- "$skill_path" 2>/dev/null)" ]; then
  echo "skill self-update: upstream changed, but '$skill_path' has local edits — NOT auto-updating."
  echo "  Preserve or discard those skill-local edits, then rerun this updater."
  exit 0
fi

if [ -n "$(git -C "$repo" log --format=%H "origin/$def..HEAD" -- "$skill_path" 2>/dev/null)" ]; then
  echo "skill self-update: this branch has committed changes to '$skill_path' not on origin/$def — NOT auto-updating."
  exit 0
fi

behind="$(git -C "$repo" rev-list --count "HEAD..origin/$def" -- "$skill_path" 2>/dev/null || echo 0)"
if git -C "$repo" restore --source "origin/$def" --worktree -- "$skill_path" 2>/dev/null; then
  echo "skill self-update: synced '$skill_path' from origin/$def ($behind affecting commit(s)) — re-read SKILL.md before proceeding."
else
  echo "skill self-update: upstream changed but the skill subtree could not be restored — using local copy."
fi
exit 0

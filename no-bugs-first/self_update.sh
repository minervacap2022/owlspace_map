#!/usr/bin/env bash
# Self-update this skill from its GitHub origin, run as Step 0 every time the
# skill is invoked (see SKILL.md). Clean-only: pulls only when the checkout is
# clean AND on the default branch; otherwise it advises and leaves the working
# tree byte-for-byte untouched — it must never disturb a sibling agent's
# uncommitted work or a feature branch (e.g. a shared dev checkout).
#
# Fail-soft on every external failure (offline, not a git checkout): the skill
# must still run from the local copy when GitHub is unreachable. Exit is always 0
# so a self-update never blocks the skill.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel 2>/dev/null)" || {
  echo "skill self-update: not a git checkout — using local copy"; exit 0; }

# Resolve the default branch from origin/HEAD; fall back to main.
def="$(git -C "$repo" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@')"
def="${def:-main}"

git -C "$repo" fetch --quiet origin "$def" 2>/dev/null || {
  echo "skill self-update: fetch failed (offline?) — using local copy"; exit 0; }

behind="$(git -C "$repo" rev-list --count "HEAD..origin/$def" 2>/dev/null || echo 0)"
if [ "$behind" = "0" ]; then
  echo "skill self-update: up to date"
  exit 0
fi

branch="$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")"
dirty=""
[ -n "$(git -C "$repo" status --porcelain 2>/dev/null)" ] && dirty=1

if [ -n "$dirty" ] || [ "$branch" != "$def" ]; then
  why="$([ "$branch" != "$def" ] && echo "on branch '$branch'" || echo "working tree is dirty")"
  echo "skill self-update: $behind new commit(s) on origin/$def, but the checkout $why — NOT auto-updating."
  echo "  When safe, run:  git -C \"$repo\" pull --ff-only origin $def"
  exit 0
fi

if git -C "$repo" pull --ff-only --quiet origin "$def" 2>/dev/null; then
  echo "skill self-update: pulled $behind commit(s) from origin/$def — re-read SKILL.md before proceeding."
else
  echo "skill self-update: $behind new commit(s) upstream but ff-pull failed (diverged?) — run git pull manually."
fi
exit 0

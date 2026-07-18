#!/usr/bin/env bash
# Self-update this doctrine skill from its canonical GitHub origin. Availability
# failures remain fail-soft; trust failures refuse replacement and keep the
# already-vetted local copy. Genuine skill-local edits are never overwritten.
set -uo pipefail

CANONICAL_HOST="github.com"
CANONICAL_REPO="minervacap2022/owlspace_map"
CANONICAL_REF="main"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_raw="$(git -C "$here" rev-parse --show-toplevel 2>/dev/null)" || {
  echo "skill self-update: not a git checkout — using local copy"; exit 0; }
repo="$(cd "$repo_raw" && pwd -P)"
skill_path="${here#"$repo"/}"

origin_url="$(git -C "$repo" remote get-url origin 2>/dev/null || echo "")"
origin_norm="$(printf '%s' "$origin_url" \
  | sed -E 's#^[A-Za-z][A-Za-z0-9+.-]*://##; s#^[^@/]+@##; s#:#/#; s#/+$##; s#\.git$##' \
  | tr '[:upper:]' '[:lower:]')"
canonical_norm="$(printf '%s/%s' "$CANONICAL_HOST" "$CANONICAL_REPO" | tr '[:upper:]' '[:lower:]')"
if [ "$origin_norm" != "$canonical_norm" ]; then
  echo "skill self-update: origin is '$origin_url' (not $CANONICAL_HOST/$CANONICAL_REPO) —" \
       "refusing to self-update from an unverified remote. Using local copy."
  exit 0
fi

remote_head="$(git -C "$repo" ls-remote --symref origin HEAD 2>/dev/null \
  | sed -n 's#^ref:[[:space:]]*refs/heads/\([^[:space:]]*\)[[:space:]]*HEAD$#\1#p')"
if [ -z "$remote_head" ]; then
  echo "skill self-update: remote default branch unavailable (offline or origin unreachable) — using local copy"
  exit 0
fi
if [ "$remote_head" != "$CANONICAL_REF" ]; then
  echo "skill self-update: remote default branch is '$remote_head', not the canonical ref" \
       "'$CANONICAL_REF' — refusing to self-update from an unverified ref. Using local copy."
  exit 0
fi

git -C "$repo" fetch --quiet origin "$CANONICAL_REF" 2>/dev/null || {
  echo "skill self-update: network unavailable or origin unreachable — using local copy"; exit 0; }

if git -C "$repo" diff --quiet "origin/$CANONICAL_REF" -- "$skill_path" 2>/dev/null; then
  echo "skill self-update: up to date"
  exit 0
fi

if ! git -C "$repo" diff --quiet HEAD -- "$skill_path" 2>/dev/null \
  || [ -n "$(git -C "$repo" ls-files --others --exclude-standard -- "$skill_path" 2>/dev/null)" ]; then
  echo "skill self-update: upstream changed, but '$skill_path' has local edits — NOT auto-updating."
  echo "  Preserve or discard those skill-local edits, then rerun this updater."
  exit 0
fi

if [ -n "$(git -C "$repo" log --format=%H "origin/$CANONICAL_REF..HEAD" -- "$skill_path" 2>/dev/null)" ]; then
  echo "skill self-update: this branch has committed changes to '$skill_path' not on origin/$CANONICAL_REF — NOT auto-updating."
  exit 0
fi

behind="$(git -C "$repo" rev-list --count "HEAD..origin/$CANONICAL_REF" -- "$skill_path" 2>/dev/null || echo 0)"
if git -C "$repo" restore --source "origin/$CANONICAL_REF" --worktree -- "$skill_path" 2>/dev/null; then
  echo "skill self-update: synced '$skill_path' from verified origin/$CANONICAL_REF ($behind affecting commit(s)) — re-read SKILL.md before proceeding."
else
  echo "skill self-update: upstream changed but the skill subtree could not be restored — using local copy."
fi
exit 0

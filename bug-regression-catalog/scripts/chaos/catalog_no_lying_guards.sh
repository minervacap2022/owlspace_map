#!/usr/bin/env bash
# Chaos runner for BUG-2026-06-03-461e97: a catalog lint with a `pattern` but the
# wrong key shape (no rule/message, and not presence:required) routes to NEITHER
# lint_patterns() (forbidden) NOR required_guards() (presence:required) — a LYING
# GUARD, enforced nowhere, silently. This is the THIRD loader meta-bug, after the
# dict-shaped-lint crash and the unknown-project silent drop.
#
# Detection is the loader invariant test, not a source pattern (the failure is
# structural — a lint rule can't see its own mis-shape). If this fails, some
# catalog entry's lint provides ZERO coverage while appearing to guard a bug.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1   # → scripts/ (where load_catalog.py lives)
T=CatalogLoaderInvariants.test_every_pattern_bearing_lint_is_actually_enforced
if python3 test_load_catalog.py "$T" >/tmp/lying_guard.log 2>&1; then
  echo "CHAOS PASSED — every catalog lint with a pattern routes to an enforcement path."; exit 0
fi
echo "CHAOS FAILED — a catalog lint is enforced nowhere (lying guard):"
cat /tmp/lying_guard.log
exit 1

#!/usr/bin/env bash
# Chaos runner for BUG-2026-06-03-df0347: default_profile must AUTO-DETECT the
# dominant language so a fresh non-Python repo gets real cross-sector edges, not an
# empty blast radius from a hardcoded lang:py. Detection = the sector_map DominantLang
# suite (a Go ui→core edge + a TS relative edge must resolve; Python stays py_stem).
set -uo pipefail

cd "$(dirname "$0")/../../../sector_map" || exit 1   # → owlspace_map/sector_map
if python3 test_extract.py DominantLang >/tmp/domlang.log 2>&1; then
  echo "CHAOS PASSED — default_profile detects language + resolves cross-sector edges."; exit 0
fi
echo "CHAOS FAILED — default_profile language detection regressed:"
cat /tmp/domlang.log
exit 1

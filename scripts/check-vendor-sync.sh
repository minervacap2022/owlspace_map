#!/usr/bin/env bash
# Guard: the engine's ONE home is this repo (sector_map/). The OwlSpace app vendors a
# copy at apps/owlspace/resources/sector_map — that copy must be byte-identical for the
# shared core files, or we re-grow the exact SSOT drift this repo exists to kill
# (Principle 0; incident: bound_profile shipped vendored-only, upstream went stale).
#
# Usage: scripts/check-vendor-sync.sh [path-to-owl-agent-repo]
# Exits 0 in-sync / when the vendor dir is absent (CI machines without the app repo);
# exits 1 listing drifted files when both exist and differ.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="${1:-$HOME/Owlspace_re}/apps/owlspace/resources/sector_map"
CORE_FILES=(extract.py cli.py server.py collectors.py scip_ingest.py graphify_ingest.py)

if [ ! -d "$VENDOR" ]; then
  echo "vendor-sync: $VENDOR absent — skipping (not an error off the app machine)"
  exit 0
fi

drift=0
for f in "${CORE_FILES[@]}"; do
  if ! diff -q "$HERE/sector_map/$f" "$VENDOR/$f" >/dev/null 2>&1; then
    echo "DRIFT: sector_map/$f != $VENDOR/$f"
    drift=1
  fi
done

if [ "$drift" -ne 0 ]; then
  echo ""
  echo "The engine has ONE home: owlspace_map/sector_map. Fix by syncing the canonical"
  echo "file to the other side (decide which direction holds the newer truth FIRST):"
  echo "  cp owlspace_map/sector_map/<f> $VENDOR/<f>   # repo → app (normal)"
  exit 1
fi
echo "vendor-sync: all ${#CORE_FILES[@]} core files identical ✓"

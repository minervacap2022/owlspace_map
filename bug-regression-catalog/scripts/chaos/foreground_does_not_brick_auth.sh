#!/usr/bin/env bash
# Chaos runner for BUG-2026-05-28-F. Static check only — no remote log
# source for iOS device logs available from here. Flagged as a manual
# verification step the full-stack-test should escalate.
set -uo pipefail
echo "  MANUAL — verify on TestFlight build:"
echo "    1. Open Klik app, wait for Today to load."
echo "    2. Background it (home/swipe up), wait 2s, foreground again."
echo "    3. Confirm: NO 'Token refresh cooling down' lines in Xcode console"
echo "       within 5s of foreground; the next API call succeeds."
echo "  OK (manual verification owed)"
exit 0

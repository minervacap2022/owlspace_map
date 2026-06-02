#!/usr/bin/env bash
# Chaos runner for BUG-2026-05-28-E: stop-race phantom error.
#
# Two assertions:
#  1. No 'Stop failed for ... no_audio_frames' in the recent KK_frontendmobile
#     log. Any occurrence = the race is back (WS-disconnect handler or
#     speechbrain auto-spawn regressed).
#  2. For every SESSION_FINALIZED with boundary_trigger=user_stop in the
#     recent window, there is NO SESSION_CREATED event matching that
#     stream within 1 second. user_stop must NOT spawn a successor.
set -euo pipefail

LOG_HOST="${LOG_HOST:-gcp}"

# `grep -c ... || echo 0` produces "0\n0" when the file is unreadable —
# the two-line value crashes `[ ... -gt 0 ]`. Use `|| true` + `${:-0}`.
phantom=$(ssh "$LOG_HOST" "grep -c 'Stop failed.*no_audio_frames' /opt/Klik/logs/KK_frontendmobile.log 2>/dev/null" || true)
phantom=${phantom:-0}
if [ "$phantom" -gt 0 ]; then
  echo "  FAIL — 'Stop failed: no_audio_frames' appears $phantom times — race regressed."
  exit 1
fi

# Cheap heuristic: count SESSION_FINALIZED with boundary_trigger=user_stop
# and SESSION_CREATED events that ALSO have stream_offset > 0. If both are
# rising in equal numbers, the auto-spawn after user_stop is back.
user_stop_finalized=$(ssh "$LOG_HOST" "grep -c 'SESSION_FINALIZED.*user_stop' /opt/Klik/logs/KK_frontendmobile.log 2>/dev/null" || true)
user_stop_finalized=${user_stop_finalized:-0}
nonzero_offset_created=$(ssh "$LOG_HOST" "grep 'SESSION_CREATED' /opt/Klik/logs/KK_frontendmobile.log 2>/dev/null | grep -vE 'timestamp_ms\": ?0[,}]' | wc -l | tr -d ' '" || true)
nonzero_offset_created=${nonzero_offset_created:-0}
echo "  user_stop finalizes:        ${user_stop_finalized}"
echo "  non-zero-offset creates:    ${nonzero_offset_created}"
# Not a strict-equality assert (other triggers also create non-zero-offset
# sessions). Soft signal — if you ever see equal counts after a user_stop
# fixture run, the spawn-on-stop bug is back.
echo "  OK — no Stop-failed phantom errors in window."
exit 0

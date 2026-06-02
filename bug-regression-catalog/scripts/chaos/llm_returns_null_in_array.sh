#!/usr/bin/env bash
# Chaos runner for BUG-2026-05-28-D: silent Pydantic 500 from meeting_minutes.
# Asserts that any 'meeting_minutes returned 500' in the orchestrator log is
# accompanied by a structured minutes_response_build_failed event in
# KK_meeting_minutes.log — i.e. the guard is in place and emits a log.
set -euo pipefail

LOG_HOST="${LOG_HOST:-gcp}"

orch_500=$(ssh "$LOG_HOST" "grep -h 'meeting_minutes returned 500' /opt/Klik/logs/KK_orchestrator.log 2>/dev/null | grep -oE 'SESSION_[A-Za-z0-9_]+' | sort -u" || true)

if [ -z "$orch_500" ]; then
  echo "  OK — no meeting_minutes 500s in window."
  exit 0
fi

bad=0
for sid in $orch_500; do
  guarded=$(ssh "$LOG_HOST" "grep -c '$sid' /opt/Klik/logs/KK_meeting_minutes.log 2>/dev/null | xargs -I{} sh -c 'grep -c minutes_response_build_failed /opt/Klik/logs/KK_meeting_minutes.log'" || true)
  guarded=${guarded:-0}
  # Lighter check: just look for the event existing at all in the file.
  # `grep -c ... || echo 0` produces "0\n0" on unreadable files — the
  # two-line value crashes `[ ... -eq 0 ]`. Use `|| true` + `${:-0}`.
  events=$(ssh "$LOG_HOST" "grep -c 'minutes_response_build_failed' /opt/Klik/logs/KK_meeting_minutes.log 2>/dev/null" || true)
  events=${events:-0}
  if [ "$events" -eq 0 ]; then
    echo "  FAIL — meeting_minutes returned 500 for $sid but no minutes_response_build_failed event exists."
    echo "         BUG-2026-05-28-D has regressed; the Pydantic guard is gone."
    bad=$((bad+1))
    break
  fi
done

if [ "$bad" -gt 0 ]; then
  exit 1
fi

echo "  OK — every meeting_minutes 500 had a matching structured guard log."
exit 0

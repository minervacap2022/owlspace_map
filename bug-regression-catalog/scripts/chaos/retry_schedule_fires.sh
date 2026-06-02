#!/usr/bin/env bash
# Chaos runner for BUG-2026-05-28-B: orchestrator retry from sync threadpool.
# Asserts that whenever pipeline_asr_auto_retry_scheduled appears, a
# matching session_id eventually shows pipeline_completed OR
# pipeline_asr_retry_exhausted — never silence.
set -euo pipefail

LOG_HOST="${LOG_HOST:-gcp}"

# Pull scheduled-retry session IDs from the last $WINDOW_HOURS (default 24)
# of orchestrator logs. Pre-fix sessions whose retries never resolved
# are stale data and should not fire the runner.
WINDOW_HOURS="${RETRY_WINDOW_HOURS:-24}"
scheduled=$(ssh "$LOG_HOST" "
  cutoff=\$(date -u -d \"${WINDOW_HOURS} hours ago\" +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -v-${WINDOW_HOURS}H +%Y-%m-%dT%H:%M:%S);
  awk -v cutoff=\"\$cutoff\" 'match(\$0, /\"@timestamp\": \"([^\"]+)\"/, m) && m[1] >= cutoff && /pipeline_asr_auto_retry_scheduled/ { if (match(\$0, /SESSION_[A-Za-z0-9_]+/)) print substr(\$0, RSTART, RLENGTH) }' /opt/Klik/logs/KK_orchestrator.log 2>/dev/null | sort -u
" || true)
# Time-window filter: only count occurrences in the last 24h. Without
# this, stale pre-fix log entries (the fix landed 2026-05-28) keep
# firing the runner forever even though the bug is healed.
# `grep -c ... || echo 0` produces "0\n0" on unreadable files — the
# two-line value crashes `[ ... -gt 0 ]`. Use `|| true` + `${:-0}`.
WINDOW_HOURS="${RETRY_WINDOW_HOURS:-24}"
schedule_failed=$(ssh "$LOG_HOST" "
  cutoff=\$(date -u -d \"${WINDOW_HOURS} hours ago\" +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -v-${WINDOW_HOURS}H +%Y-%m-%dT%H:%M:%S);
  awk -v cutoff=\"\$cutoff\" 'match(\$0, /\"@timestamp\": \"([^\"]+)\"/, m) { if (m[1] >= cutoff && /pipeline_asr_retry_schedule_failed/) c++ } END { print c+0 }' /opt/Klik/logs/KK_orchestrator.log 2>/dev/null
" || true)
schedule_failed=${schedule_failed:-0}

if [ "$schedule_failed" -gt 0 ]; then
  echo "  FAIL — pipeline_asr_retry_schedule_failed appears $schedule_failed times."
  echo "         BUG-2026-05-28-B has regressed; the retry scheduler is broken."
  exit 1
fi

if [ -z "$scheduled" ]; then
  echo "  SKIP — no auto-retries scheduled in window (nothing to verify)."
  exit 0
fi

stuck=0
for sid in $scheduled; do
  # `|| true` guards against set -e firing when no matches exist
  # (grep -cE exits 1 on empty input even though it prints "0").
  outcome=$(ssh "$LOG_HOST" "grep -h '$sid' /opt/Klik/logs/KK_orchestrator.log 2>/dev/null | grep -cE 'pipeline_completed|pipeline_asr_retry_exhausted'" || true)
  outcome=${outcome:-0}
  if [ "$outcome" -eq 0 ]; then
    echo "  FAIL — scheduled retry never resolved for $sid"
    stuck=$((stuck+1))
  fi
done

if [ "$stuck" -gt 0 ]; then
  exit 1
fi

echo "  OK — every scheduled retry resolved (completed or exhausted)."
exit 0

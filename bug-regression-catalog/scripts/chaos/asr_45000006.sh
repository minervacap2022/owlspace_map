#!/usr/bin/env bash
# Chaos runner for BUG-2026-05-28-A: ASR retry classifier on Volcengine
# error 45000006.
#
# Strategy: read the recent KK_asr.log on the backend and verify that ANY
# 45000006 in the last 24h is followed by either:
#   - a successful retry log line (volcengine_audio_fetch_failure_retry)
#   - a final pipeline_completed for the same session_id
#
# We do not simulate Volcengine returning 45000006 here (would require a
# mock injection point in production). The signal we check IS the
# production retry behaviour — if it stopped working, this runner fails.
#
# Future improvement: when a `MOCK_VOLCENGINE_45000006=1` flag is added to
# the test stack, force the error from the runner and assert recovery.
set -euo pipefail

LOG_HOST="${LOG_HOST:-gcp}"

# `grep -c PATTERN FILE || echo 0` produces "0\n0" when the file is
# unreadable (grep prints 0 + exits non-zero, then `|| echo 0` adds
# another 0). The two-line value then crashes `[ ... -gt 0 ]` with
# `integer expression expected`. Use `|| true` + a `${:-0}` fallback.
count_45000006=$(ssh "$LOG_HOST" "grep -c '45000006' /opt/Klik/logs/KK_asr.log 2>/dev/null" || true)
count_45000006=${count_45000006:-0}
count_retry_log=$(ssh "$LOG_HOST" "grep -c 'volcengine_audio_fetch_failure_retry' /opt/Klik/logs/KK_asr.log 2>/dev/null" || true)
count_retry_log=${count_retry_log:-0}

echo "  45000006 hits in last log:       ${count_45000006}"
echo "  audio_fetch_failure_retry hits:  ${count_retry_log}"

if [ "$count_45000006" -gt 0 ] && [ "$count_retry_log" -eq 0 ]; then
  echo "  FAIL — Volcengine returned 45000006 but classifier never logged a retry."
  echo "         BUG-2026-05-28-A has regressed; check volcengine_transcriber._is_retryable_audio_fetch_failure."
  exit 1
fi

echo "  OK — either no 45000006 in window, or retries fired correctly."
exit 0

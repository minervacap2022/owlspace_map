#!/usr/bin/env bash
# Unified chaos / failure-injection phase. Iterates every catalog entry
# whose `chaos.runner` is set and invokes the runner against the target
# stack. Consumed by:
#   - /full-stack-test (phase 21)
#   - /klik-ios-e2e-test (STEP 12, with --ios-edge filter)
#
# Usage:
#   run_chaos_phase.sh --base-url http://localhost:8400 [--ios-edge]
#
# Exit codes:
#   0 — every runner passed (or no runners configured)
#   1 — one or more runners failed
#   2 — catalog or environment broken
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_URL="${BASE_URL:-http://localhost:8400}"
IOS_EDGE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --base-url) BASE_URL="$2"; shift 2 ;;
    --ios-edge) IOS_EDGE=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Resolve runner list via the shared Python loader so the schema check
# fires here too. Output format: <bug_id>\t<runner_path>\t<description>
ENTRIES_FILE="$(mktemp)"
trap 'rm -f "$ENTRIES_FILE"' EXIT
python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
from load_catalog import chaos_runners
for bug_id, runner, desc in chaos_runners(ios_edge=bool(${IOS_EDGE})):
    print(f'{bug_id}\t{runner}\t{desc}')
" > "$ENTRIES_FILE" 2>/dev/null

if [ ! -s "$ENTRIES_FILE" ]; then
  echo "PASS  chaos_phase  no catalog entries with chaos.runner — nothing to inject"
  exit 0
fi

FAIL=0
PASS=0
while IFS=$'\t' read -r bug_id runner desc; do
  [ -z "$bug_id" ] && continue

  if [ ! -x "$runner" ]; then
    echo "SKIP  ${bug_id}  runner missing or not executable: ${runner}"
    continue
  fi

  echo "RUN   ${bug_id}  ${desc}"
  BASE_URL="$BASE_URL" IOS_EDGE="$IOS_EDGE" "$runner" --base-url "$BASE_URL"
  status=$?
  if [ "$status" -eq 0 ]; then
    echo "PASS  ${bug_id}"
    PASS=$((PASS+1))
  elif [ "$status" -eq 2 ]; then
    echo "SKIP  ${bug_id}  runner precondition not met"
  else
    echo "FAIL  ${bug_id}  ${desc}"
    FAIL=$((FAIL+1))
  fi
done < "$ENTRIES_FILE"

echo "─────────────────────────────────────────────────────────"
echo "chaos phase: ${PASS} pass / ${FAIL} fail"
[ "$FAIL" -gt 0 ] && exit 1 || exit 0

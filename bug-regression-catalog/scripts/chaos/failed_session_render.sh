#!/usr/bin/env bash
# Chaos runner for BUG-2026-05-28-C: failed-session title fabrication.
# Calls /api/v1/meetings as the seeded test user and asserts that any
# session with status="failed" carries title="" (never a fabricated date).
set -uo pipefail

BASE_URL="${BASE_URL:-https://hiklik.ai}"
JWT="${IOS_E2E_JWT:-}"

if [ -z "$JWT" ]; then
  echo "  SKIP — IOS_E2E_JWT not set (runner needs a logged-in token)."
  exit 2
fi

resp=$(curl -fsS --max-time 10 "${BASE_URL}/api/v1/meetings?limit=50" \
  -H "Authorization: Bearer $JWT") || {
    echo "  FAIL — /api/v1/meetings returned non-200"; exit 1; }

check=$(printf '%s' "$resp" | python3 -c "
import json, sys
data = json.load(sys.stdin)
failed = [i for i in data.get('items', []) if (i.get('status') or '').lower() == 'failed']
print(f'FAILED_COUNT\t{len(failed)}')
for i in failed:
    title = (i.get('title') or '').strip()
    if title:
        print(f'VIOLATION\t{i.get("id")}\t{title}')
")
failed_count=$(printf '%s\n' "$check" | awk -F'\t' '$1 == "FAILED_COUNT" {print $2}')
violations=$(printf '%s\n' "$check" | awk -F'\t' '$1 == "VIOLATION" {print $2 "\t" $3}')

if [ "${failed_count:-0}" -eq 0 ]; then
  echo "  SKIP — no failed sessions in /api/v1/meetings response (nothing to verify)."
  exit 2
fi

if [ -n "$violations" ]; then
  echo "  FAIL — failed sessions returned non-empty title (BUG-2026-05-28-C regressed):"
  printf '%s\n' "$violations" | head -5
  exit 1
fi

echo "  OK — every failed session has empty title; iOS will render explicit state."
exit 0

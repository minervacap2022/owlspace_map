#!/usr/bin/env bash
# Chaos runner for BUG-2026-05-28-C: failed-session title fabrication.
# Calls /api/v1/meetings as the seeded test user and asserts that any
# session with status="failed" carries title="" (never a fabricated date).
set -uo pipefail

BASE_URL="${BASE_URL:-https://hiklik.ai}"
JWT="${IOS_E2E_JWT:-}"

if [ -z "$JWT" ]; then
  echo "  SKIP — IOS_E2E_JWT not set (runner needs a logged-in token)."
  exit 0
fi

resp=$(curl -fsS --max-time 10 "${BASE_URL}/api/v1/meetings?limit=50" \
  -H "Authorization: Bearer $JWT") || {
    echo "  FAIL — /api/v1/meetings returned non-200"; exit 1; }

violations=$(printf '%s' "$resp" | python3 -c "
import json, sys
data = json.load(sys.stdin)
bad = [
    (i.get('id'), i.get('title'))
    for i in data.get('items', [])
    if (i.get('status') or '').lower() == 'failed' and (i.get('title') or '').strip()
]
for sid, title in bad:
    print(f'{sid}\t{title}')
")

if [ -n "$violations" ]; then
  echo "  FAIL — failed sessions returned non-empty title (BUG-2026-05-28-C regressed):"
  printf '%s\n' "$violations" | head -5
  exit 1
fi

echo "  OK — every failed session has empty title; iOS will render explicit state."
exit 0

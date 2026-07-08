#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/chaos/failed_session_render.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

cat > "$tmp/curl" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$CAPTURE"
case " $* " in
  *" Authorization: Bearer test-token "*) ;;
  *) echo "missing auth header" >&2; exit 22 ;;
esac
case " $* " in
  *" X-Timezone: America/Los_Angeles "*) ;;
  *) echo "missing timezone header" >&2; exit 22 ;;
esac
cat <<'JSON'
{"items":[{"id":"session_failed","status":"failed","title":""}]}
JSON
SH
chmod +x "$tmp/curl"

CAPTURE="$tmp/curl.args" \
PATH="$tmp:$PATH" \
IOS_E2E_JWT="test-token" \
IOS_E2E_TIMEZONE="America/Los_Angeles" \
BASE_URL="https://example.invalid" \
  bash "$RUNNER" > "$tmp/out" 2>&1

grep -q "OK — every failed session has empty title" "$tmp/out"
grep -q "X-Timezone: America/Los_Angeles" "$tmp/curl.args"

echo "PASS failed-session chaos runner sends the mobile timezone header"

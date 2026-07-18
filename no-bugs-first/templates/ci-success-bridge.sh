#!/usr/bin/env bash
# Post the single `ci-success` evidence context from self-hosted Woodpecker using
# the klik-cicd GitHub App. Required tools: bash, openssl, curl, jq, base64.
set -euo pipefail

STATE="${1:?usage: ci-success-bridge.sh <success|failure|error|pending>}"
REPO="${CI_REPO:?CI_REPO not set}"
SHA="${CI_COMMIT_SHA:?CI_COMMIT_SHA not set}"
APP_ID="${NEXORA_APP_ID:?NEXORA_APP_ID not set}"
TARGET_URL="${CI_PIPELINE_URL:-}"
CONTEXT="ci-success"

if [ -n "${NEXORA_APP_PRIVATE_KEY_FILE:-}" ]; then
  KEY_FILE="$NEXORA_APP_PRIVATE_KEY_FILE"
elif [ -n "${NEXORA_APP_PRIVATE_KEY:-}" ]; then
  KEY_FILE="$(mktemp)"
  printf '%s' "$NEXORA_APP_PRIVATE_KEY" > "$KEY_FILE"
  trap 'rm -f "$KEY_FILE"' EXIT
else
  echo "no NEXORA_APP_PRIVATE_KEY[_FILE] provided" >&2
  exit 1
fi

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

now="$(date +%s)"
iat="$((now - 60))"
exp="$((now + 540))"
header='{"alg":"RS256","typ":"JWT"}'
payload="$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "$iat" "$exp" "$APP_ID")"
unsigned="$(printf '%s' "$header" | b64url).$(printf '%s' "$payload" | b64url)"
signature="$(printf '%s' "$unsigned" | openssl dgst -sha256 -sign "$KEY_FILE" | b64url)"
jwt="$unsigned.$signature"

api() {
  curl -fsSL -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" "$@"
}

installation_id="$(api -H "Authorization: Bearer $jwt" \
  "https://api.github.com/repos/${REPO}/installation" | jq -r '.id')"
[ -n "$installation_id" ] && [ "$installation_id" != "null" ] || {
  echo "no GitHub App installation for $REPO" >&2; exit 1; }

token="$(api -X POST -H "Authorization: Bearer $jwt" \
  "https://api.github.com/app/installations/${installation_id}/access_tokens" | jq -r '.token')"
[ -n "$token" ] && [ "$token" != "null" ] || {
  echo "could not mint installation token" >&2; exit 1; }

description="Woodpecker pipeline ${STATE}"
api -X POST -H "Authorization: token $token" \
  "https://api.github.com/repos/${REPO}/statuses/${SHA}" \
  -d "$(jq -nc --arg state "$STATE" --arg context "$CONTEXT" \
    --arg description "$description" --arg target_url "$TARGET_URL" \
    '{state:$state, context:$context, description:$description} + (if $target_url=="" then {} else {target_url:$target_url} end)')" \
  >/dev/null

echo "posted ci-success=$STATE for ${REPO}@${SHA:0:8}"

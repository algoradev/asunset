#!/usr/bin/env bash
# Incident freeze/unfreeze for a feature — the runbook invocation that
# ships IN LOCKSTEP with the endpoint (spec §10; a freeze endpoint
# nobody can invoke correctly at 2am is a half-built incident story).
#
# Runs ON THE DEPLOYMENT BOX (SSH over tailnet). Token custody is
# pre-solved: the machine operator identity is the asunset-api service
# account, whose client credentials are already in the box's .env —
# no human token juggling under incident stress.
#
# Usage (from the repo/consumer root containing .env):
#   tools/ops/feature-freeze.sh freeze   <feature-key> [reason...]
#   tools/ops/feature-freeze.sh unfreeze <feature-key>
#   tools/ops/feature-freeze.sh status
set -euo pipefail

CMD="${1:?usage: feature-freeze.sh freeze|unfreeze|status <key> [reason]}"
KEY="${2:-}"
shift $(( $# > 1 ? 2 : 1 )) || true
REASON="${*:-}"

ENV_FILE="${ENV_FILE:-.env}"
[ -f "$ENV_FILE" ] || { echo "FATAL: $ENV_FILE not found — run from the deployment root" >&2; exit 1; }
get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }

KC_URL="${KC_INTERNAL_OVERRIDE:-$(get KEYCLOAK_INTERNAL_URL)}"
REALM="$(get KEYCLOAK_REALM)"
CLIENT_ID="$(get KEYCLOAK_API_CLIENT_ID)"
CLIENT_SECRET="$(get KEYCLOAK_API_CLIENT_SECRET)"
API_URL="${API_URL:-http://localhost:$(get API_PORT || echo 8000)}"

# In-network Keycloak DNS (keycloak:8080) isn't resolvable from the
# host — default to localhost:8080 unless overridden.
case "$KC_URL" in http://keycloak:8080*) KC_URL="http://localhost:8080${KC_URL#http://keycloak:8080}";; esac

TOKEN=$(curl -sf -X POST "$KC_URL/realms/$REALM/protocol/openid-connect/token" \
  -d "grant_type=client_credentials&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])") \
  || { echo "FATAL: could not obtain operator token (check KC url/credentials)" >&2; exit 1; }

case "$CMD" in
  freeze)
    [ -n "$KEY" ] || { echo "FATAL: feature key required" >&2; exit 1; }
    curl -sf -X POST "$API_URL/platform/features/$KEY/freeze" \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
      -d "{\"reason\": \"${REASON:-incident freeze via runbook}\"}" | python3 -m json.tool
    ;;
  unfreeze)
    [ -n "$KEY" ] || { echo "FATAL: feature key required" >&2; exit 1; }
    curl -sf -X POST "$API_URL/platform/features/$KEY/unfreeze" \
      -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
    ;;
  status)
    curl -sf "$API_URL/platform/features" -H "Authorization: Bearer $TOKEN" \
      | python3 -c "import json,sys; [print(f\"{f['key']}: {'FROZEN — ' + str(f['freeze_reason']) if f['frozen'] else ('disabled' if not f['enabled'] else 'active')}\") for f in json.load(sys.stdin)]"
    ;;
  *) echo "FATAL: unknown command $CMD" >&2; exit 1;;
esac

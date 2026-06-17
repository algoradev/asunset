#!/usr/bin/env bash
# Keycloak post-import bootstrap — runs once per `up` after the realm
# import completes. Mounted into the keycloak-init container by every
# overlay so behavior diffs by env var, not by replacing the script.
#
# Why a script and not inline `command:` blocks: docker compose merges
# `command:` as REPLACE, not append. Inline scripts in compose.yml meant
# every overlay had to re-paste the whole body, and any change to the
# base silently dropped on tailscale/TLS deployments. Mounting one file
# means overlays just flip env vars (KC_AUTH_URL, WEB_BASE_URL).
#
# Env contract:
#   KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD     — bootstrap creds (always set)
#   KEYCLOAK_REALM                              — realm name (always set)
#   KEYCLOAK_API_CLIENT_SECRET                  — synced into asunset-api client
#   KC_AUTH_URL   (default http://keycloak:8080) — base URL for kcadm; tailscale
#                                                  overlay sets …:8080/auth
#   WEB_BASE_URL  (optional)                    — when set, rewrite asunset-web's
#                                                  redirect_uris/web_origins to it;
#                                                  if it starts with https://, also
#                                                  lock realm sslRequired=all
#   KC_SMTP_HOST  (optional)                    — when set, configure realm SMTP;
#                                                  empty = local dev / no email

set -euo pipefail

KC_AUTH_URL="${KC_AUTH_URL:-http://keycloak:8080}"
KCADM=/opt/keycloak/bin/kcadm.sh

"$KCADM" config credentials \
  --server "$KC_AUTH_URL" \
  --realm master \
  --user "$KEYCLOAK_ADMIN" \
  --password "$KEYCLOAK_ADMIN_PASSWORD"

# --- asunset-api: sync client secret from env ---------------------------
API_UUID="$("$KCADM" get clients -r "$KEYCLOAK_REALM" -q clientId=asunset-api --fields id --format csv --noquotes | tr -d '\r\n')"
if [ -z "$API_UUID" ]; then
  echo "keycloak-init: asunset-api client not found" >&2
  exit 1
fi
"$KCADM" update "clients/$API_UUID" \
  -r "$KEYCLOAK_REALM" \
  -s "secret=$KEYCLOAK_API_CLIENT_SECRET"
echo "keycloak-init: asunset-api secret synced from env"

# --- asunset-api service account: grant manage-users --------------------
# Required for the invite flow (create user, send actions email).
# add-roles is idempotent — `|| true` covers the "already assigned" 409.
"$KCADM" add-roles -r "$KEYCLOAK_REALM" \
  --uusername=service-account-asunset-api \
  --cclientid=realm-management \
  --rolename=manage-users 2>/dev/null || true
echo "keycloak-init: asunset-api service account has manage-users"

# --- realm: session + OTP policy ----------------------------------------
# --import-realm uses IGNORE_EXISTING on re-boots, so realm-export.json
# tweaks don't propagate after first import. Push HIPAA/NYDFS knobs via
# kcadm so they land on every start.
"$KCADM" update "realms/$KEYCLOAK_REALM" \
  -s "ssoSessionIdleTimeout=900" \
  -s "ssoSessionMaxLifespan=14400" \
  -s "otpPolicyType=totp" \
  -s "otpPolicyAlgorithm=HmacSHA1" \
  -s "otpPolicyDigits=6" \
  -s "otpPolicyPeriod=30" \
  -s "otpPolicyLookAheadWindow=1"
echo "keycloak-init: realm session + OTP policy updated"

# --- asunset-web: rewrite URIs to deployment hostname -------------------
# The realm export ships dev-default URIs (http://localhost:3000 +
# :5173). Every non-plain deployment MUST overwrite them or Keycloak
# rejects login with an opaque "Invalid parameter: redirect_uri".
#
# The TLS/tailscale overlays set WEB_BASE_URL directly. But relying on a
# single var threading through a compose overlay is fragile: if it's
# unset for any reason on a remote deploy, the client silently keeps the
# localhost dev URIs (wirebit-crm-client hit exactly this on the first
# tailnet bootstrap). So: derive WEB_BASE_URL from TAILSCALE_HOST when
# it's not already set, and refuse to leave localhost URIs on a clearly
# remote (tailnet) deployment rather than failing silently at login.
WEB_BASE_URL="${WEB_BASE_URL:-}"
if [ -z "$WEB_BASE_URL" ] && [ -n "${TAILSCALE_HOST:-}" ]; then
  WEB_BASE_URL="https://${TAILSCALE_HOST}"
  echo "keycloak-init: derived WEB_BASE_URL=$WEB_BASE_URL from TAILSCALE_HOST"
fi

# Fail loud on the landmine: a tailnet deploy (TAILSCALE_HOST set) whose
# resolved web base is still localhost would ship broken redirect URIs.
# Stop here with a clear message instead of a runtime login failure.
case "$WEB_BASE_URL" in
  http://localhost*|http://127.0.0.1*|"")
    if [ -n "${TAILSCALE_HOST:-}" ]; then
      echo "keycloak-init: FATAL — TAILSCALE_HOST=$TAILSCALE_HOST but WEB_BASE_URL resolved to '${WEB_BASE_URL:-<empty>}'; refusing to configure asunset-web with localhost redirect URIs (would reject login with 'Invalid parameter: redirect_uri')" >&2
      exit 1
    fi
    ;;
esac

if [ -n "$WEB_BASE_URL" ]; then
  WEB_UUID="$("$KCADM" get clients -r "$KEYCLOAK_REALM" -q clientId=asunset-web --fields id --format csv --noquotes | tr -d '\r\n')"
  "$KCADM" update "clients/$WEB_UUID" \
    -r "$KEYCLOAK_REALM" \
    -s "rootUrl=$WEB_BASE_URL" \
    -s "baseUrl=$WEB_BASE_URL" \
    -s "redirectUris=[\"$WEB_BASE_URL/*\"]" \
    -s "webOrigins=[\"$WEB_BASE_URL\"]" \
    -s "attributes.\"post.logout.redirect.uris\"=$WEB_BASE_URL/*"
  echo "keycloak-init: asunset-web URIs → $WEB_BASE_URL"

  # When the deployment terminates TLS (TLS or tailscale modes both set
  # WEB_BASE_URL to https://…), force sslRequired=all so Keycloak refuses
  # cleartext on every channel.
  case "$WEB_BASE_URL" in
    https://*)
      "$KCADM" update "realms/$KEYCLOAK_REALM" -s "sslRequired=all"
      echo "keycloak-init: realm sslRequired=all"
      ;;
  esac
fi

# --- TOTP enforcement on platform_admin holders -------------------------
# HIPAA §164.312(a)(2)(i) / NYDFS 500.12 — MFA on privileged accounts.
# Skip users who already have a TOTP credential — overwriting
# requiredActions on an enrolled user forces re-enrollment, which piles
# up orphan credentials and makes the OTP picker nondeterministic.
ADMIN_USERS="$("$KCADM" get "roles/platform_admin/users" -r "$KEYCLOAK_REALM" --fields username --format csv --noquotes 2>/dev/null | tr -d '\r"')"
for U in $ADMIN_USERS; do
  [ -z "$U" ] && continue
  # NB: can't use the name UID — readonly bash built-in (effective user
  # id); assignment silently aborts the whole script under `set -e`.
  USER_UID="$("$KCADM" get users -r "$KEYCLOAK_REALM" -q "username=$U" --fields id --format csv --noquotes | tr -d '\r\n"')"
  [ -z "$USER_UID" ] && continue
  HAS_TOTP="$("$KCADM" get "users/$USER_UID/credentials" -r "$KEYCLOAK_REALM" --fields type --format csv --noquotes 2>/dev/null | tr -d '\r"' | grep -cx 'otp' || true)"
  if [ "$HAS_TOTP" -gt 0 ]; then
    echo "keycloak-init: TOTP already enrolled for $U — skipping"
    continue
  fi
  "$KCADM" update "users/$USER_UID" \
    -r "$KEYCLOAK_REALM" \
    -s 'requiredActions=["CONFIGURE_TOTP"]' 2>/dev/null || true
  echo "keycloak-init: TOTP required for $U"
done

# --- realm SMTP ---------------------------------------------------------
# Drives Keycloak's own emails — verify-email, forgot-password, magic-link
# invites — separate from the app-side Notifier. Skip entirely if
# KC_SMTP_HOST is unset so local dev / CI never wires up real delivery by
# accident. Compatible with Resend SMTP (smtp.resend.com:587, user=resend,
# password=<api-key>, starttls=true).
#
# Bonus catch: `kcadm get realms/<realm> --fields smtpServer` returns
# `{}` on KC 25 even after a successful update — `--fields` has a quirk
# for nested objects. Values *are* persisted; verify by reading the full
# realm JSON without --fields, or trying a "Send test email" from the
# admin UI. Don't chase this red herring.
if [ -n "${KC_SMTP_HOST:-}" ]; then
  "$KCADM" update "realms/$KEYCLOAK_REALM" \
    -s "smtpServer.host=$KC_SMTP_HOST" \
    -s "smtpServer.port=${KC_SMTP_PORT:-587}" \
    -s "smtpServer.from=$KC_SMTP_FROM" \
    -s "smtpServer.fromDisplayName=${KC_SMTP_FROM_DISPLAY_NAME:-}" \
    -s "smtpServer.replyTo=${KC_SMTP_REPLY_TO:-}" \
    -s "smtpServer.ssl=${KC_SMTP_SSL:-false}" \
    -s "smtpServer.starttls=${KC_SMTP_STARTTLS:-true}" \
    -s "smtpServer.auth=${KC_SMTP_AUTH:-true}" \
    -s "smtpServer.user=${KC_SMTP_USER:-}" \
    -s "smtpServer.password=${KC_SMTP_PASSWORD:-}"
  echo "keycloak-init: realm SMTP configured ($KC_SMTP_HOST)"
else
  echo "keycloak-init: KC_SMTP_HOST unset — skipping realm SMTP (Keycloak emails disabled)"
fi

# Runbook: getting an operator token (the auth quickstart)

Exercise-2 finding: the runtime-grants surface is solid *once reached* —
reaching it is the cliff. Two identities, two paths; know which you need.

## Path 1 — the machine operator (reads + freeze tier): zero friction

For: `GET /platform/features`, roles listings, reconcile `dry_run`,
freeze/unfreeze. On the deployment box, from the deployment root:

    TOKEN=$(curl -sf -X POST "http://localhost:8080/realms/$(grep '^KEYCLOAK_REALM=' .env | cut -d= -f2)/protocol/openid-connect/token" \
      -d "grant_type=client_credentials&client_id=$(grep '^KEYCLOAK_API_CLIENT_ID=' .env | cut -d= -f2)&client_secret=$(grep '^KEYCLOAK_API_CLIENT_SECRET=' .env | cut -d= -f2)" \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['access_token'])")

This is the asunset-api service account (`platform_support`,
provisioned by keycloak-init on every start). It can NOT mutate grants
or roles — by design. `tools/ops/feature-freeze.sh` wraps this path.

## Path 2 — a human admin token (grant/role mutations)

Mutations require an org admin (or platform_admin) HUMAN token. In
production shape the human logs in through the browser — API-scripting
a human admin is a dev/staging affair, and these are the cliffs:

1. **Direct access grants are OFF on asunset-web in production** —
   intended posture. On a dev/staging realm, enable them transiently
   (Keycloak admin console → Clients → asunset-web → Capability config)
   or via kcadm.
2. **MFA will block password-only grants**: platform_admin holders get
   TOTP enforced (keycloak-init) and once enrolled, a direct grant
   needs `totp=<code>` in the form body — password alone returns
   `invalid_grant`. This is the MFA posture *working*, not a bug:

        curl -s -X POST .../token -d "grant_type=password&client_id=asunset-web&username=alice&password=...&totp=123456&scope=openid"

3. **The dev-realm TOTP ping-pong** (recurring in exercises): deleting a
   platform_admin's OTP credential makes keycloak-init re-add
   CONFIGURE_TOTP on its next run — "Account is not fully set up" on
   direct grants until cleared again. On real deployments the human
   enrolls once and this never recurs; on dev realms, expect the loop.
4. **Recovery when locked out** (dev only): the Keycloak master admin
   (`KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD` in `.env`) can reset a
   user's password, clear `requiredActions`, and delete an OTP
   credential via the admin console at `http://localhost:8080/admin`
   (or kcadm). Never do this on a client realm — that's the client
   admin's credential, not yours (trust boundary).

## Which do I need?

| Action | Identity |
|---|---|
| list features / roles, reconcile dry_run | machine (path 1) |
| freeze / unfreeze | machine (path 1) — that's the 2am design |
| grant/revoke a feature, assign/unassign a role | human admin (path 2) |
| reconcile (mutating), manifest apply | human platform_admin (path 2) |

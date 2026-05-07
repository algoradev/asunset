# asunset

Template for self-hosted, role-based, HIPAA-ready platforms. Stack:

- **Keycloak** — identity / OIDC (owns authN + platform-level realm roles)
- **OpenFGA** — fine-grained authorization (Zanzibar-style ReBAC; owns org-, team-, and resource-level permissions)
- **Postgres** — app data + keycloak data + FGA storage (three logical DBs, separate roles)
- **FastAPI** — resource server; JWT validation, RLS-scoped sessions, audit pipeline
- **React + Tailwind + shadcn/ui** — SPA with `react-oidc-context`
- **Vector** — unifies Keycloak events, OpenFGA decisions, and app audit events into one correlated stream, ready for a swappable SIEM (Wazuh overlay included)

One deployment = one `organization`. Within the org, users belong to **teams**. Resources are team-scoped by default; direct user grants and org-wide grants are both supported in the FGA model.

## Run it

```sh
cp .env.example .env            # edit if you care; defaults work locally
docker compose up -d            # boot the full stack
```

First sign-in path:

1. Open http://localhost:3000
2. Sign in as **alice / AliceDev-1234!** (realm role `platform_admin`)
3. You'll see the first-run screen — name the organization, hit "Create organization"
4. You land on the Notes page. Create a note, share it with the org.

Other seeded users: `bob / BobDev-12345!`, `carol / CarolDev-1234!` (no platform role; will see "instance not yet provisioned" until alice bootstraps and adds them).

The default `docker compose up` keeps Keycloak's `directAccessGrantsEnabled=false` on the web client — browsers use the proper auth-code + PKCE flow. API-only smoke testing requires enabling it at runtime via `kcadm`; the realm export stays locked-down.

## Dev loop

```sh
docker compose -f compose.yml -f compose.dev.yml up   # hot reload for api + web
docker compose exec api pytest                         # backend tests
```

## TLS mode

Plain `docker compose up` is HTTP-only and fine for localhost dev. Before
anything goes on a wire — even a VPN-gated LAN — flip to the TLS overlay,
which puts Caddy in front, terminates HTTPS, switches Keycloak to
production mode, and rewrites realm redirect URIs to https.

```sh
# 1. Add the TLS hostnames to your hosts file so the browser resolves them.
echo "127.0.0.1 asunset.local auth.asunset.local api.asunset.local" | sudo tee -a /etc/hosts

# 2. Rebuild web + keycloak-init with TLS-aware args, then bring everything up.
docker compose -f compose.yml -f compose.tls.yml build web keycloak-init
docker compose -f compose.yml -f compose.tls.yml up -d

# 3. Open https://asunset.local/
```

The first browser visit shows a cert warning — Caddy signs with its own
internal CA. To clear the warning for local dev, install Caddy's root CA:

```sh
docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt
# copy that PEM into your OS/browser trust store
```

**For real deployments:** replace `tls internal` in `infra/caddy/Caddyfile`
with either explicit cert files (mount them via the `caddy` service's
`volumes`) or Caddy's ACME issuer (set a valid `email` in the Caddyfile
global block and make ports 80/443 reachable from Let's Encrypt).

What flipping to TLS gets you:
- Browser ↔ {web, keycloak, api} traffic encrypted end-to-end
- HSTS + X-Content-Type-Options + X-Frame-Options on every response
- Keycloak running `start` (production mode) with `KC_HOSTNAME_STRICT=true`
- Realm `sslRequired=all`, redirect URIs scoped to the https hostname
- Direct container ports no longer bound on the host — Caddy is the only ingress

Intra-compose traffic (API ↔ Postgres / OpenFGA / Keycloak) stays HTTP.
For single-host deployments inside a VPN that's defense-in-depth territory
and the operator's call; swap `sslmode=disable` → `sslmode=verify-full`
and front each service with its own TLS sidecar if the deployment topology
demands it.

## Operate it

**FGA ↔ DB reconciliation.** The dual-write invariant is: *fail toward orphan FGA tuples, never toward phantom DB rows* — see the comment at the top of `apps/api/src/asunset_api/auth/authorizer.py`. Reconcile tooling:

```sh
# interactive, platform_admin only, audit-logged
POST /platform/reconcile-fga

# cron-friendly
docker compose exec -T api python -m asunset_api.reconcile
```

Both emit `fga.drift_detected` and `fga.drift_fixed` audit events — threshold these in your SIEM; bursts of drift indicate either a bug or an attacker bypassing the dual-write ordering.

**SIEM.** Vector ships everything. Default dev profile writes to stdout + rotating file; the Wazuh overlay adds a syslog sink:

```sh
docker compose -f compose.yml -f compose.wazuh.yml up
```

Swapping to Graylog / ELK / Splunk is a sink change in `infra/vector/wazuh.toml`, not a code change.

## Build a product on top of this

**Use the `consuming-template/` scaffold.** It's the supported path and
keeps your product code outside the asunset subtree, so routine
upstream pulls don't touch your work.

```sh
# In a fresh repo for your product:
git subtree add --prefix=vendor/asunset git@github.com:you/asunset.git main --squash
cp -r vendor/asunset/consuming-template/. .
rm -rf consuming-template/   # don't ship a self-reference
```

See `consuming-template/README.md` for the full walkthrough — what to
edit (your model, FGA types, router, alembic), what NOT to edit (JWT
validation, FGA client, audit sink), and how to keep the vendored
asunset up to date via `scripts/update-vendor.sh`.

**The old "rename Notes in place" path is no longer recommended.** It
mixes platform code with product code and guarantees painful merges
every time you pull asunset upstream. The `apps/api/` and `apps/web/`
directories of *this* repo are now read-as-reference only — they're
the working demo of every pattern the platform provides; consume them
via subtree, don't fork them.

## What this template is NOT

- Not a product. The Notes demo exists to exercise the foundation, not to be shipped.
- Not a certified HIPAA solution. Operator still signs BAAs, configures retention on the SIEM, sets up WORM storage, disables `start-dev` on Keycloak, etc. The template gives you the controls and correlation infrastructure; the compliance paperwork is yours.
- Not multi-tenant across orgs. Every deployment serves one organization. Splitting into multi-client-per-instance would require adding an `X-Org-Id` disambiguation; the RLS + tenant-column scaffolding is already there.

## Layout

```
asunset/
├── compose.yml, compose.dev.yml, compose.tls.yml, compose.tailscale.yml, compose.wazuh.yml
├── .env.example
├── install.sh                     # bootstrap docker + go + asunset CLI on a fresh host
├── apps/
│   ├── api/                       # Notes-demo backend (read as reference)
│   ├── web/                       # Notes-demo SPA (read as reference)
│   └── keycloak-theme/            # Keycloakify login theme
├── packages/
│   └── asunset_core/              # reusable Python package — consumers depend on this
├── consuming-template/            # scaffold for products built on asunset
├── tools/
│   └── deploy/                    # `asunset` CLI (init / up / down / restart / logs / ps)
└── infra/
    ├── caddy/                     # TLS reverse proxy (Caddyfile)
    ├── keycloak/                  # realm export (clients, roles, users, event listeners)
    ├── openfga/                   # (FGA model lives in apps/api for now)
    ├── postgres/                  # init script: three DBs, owner + app-user split
    └── vector/                    # log pipeline (base + wazuh overlay)
```

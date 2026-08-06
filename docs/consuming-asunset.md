# Consuming asunset — the complete guide

The one document a product team reads to build on asunset: vendoring,
composing, configuring, building, and operating. Deep dives live in
their own docs (linked throughout); **rulings made here are canonical**
— they were settled with real consumers (centum, wirebit-crm,
OpsRoom) and several are review-ratified.

What consuming asunset gets you: identity (Keycloak, OIDC, MFA
posture), authorization (OpenFGA ReBAC + Postgres RLS defense-in-depth),
the audit pipeline (correlated, SIEM-shipped, append-only), feature
permissions (manifest-driven, runtime grants, incident freeze), agent
session tokens, the platform HTTP surface (orgs/teams/invites/audit),
deploy tooling, and the test kit. Contract of record for identity:
[`identity-contract.md`](identity-contract.md).

---

## 1. Vendor it

**Pattern: `git subtree`, squashed, whole repo, off `main`.** Ruled —
no alternative is supported.

```sh
# in your product repo
git subtree add --prefix=vendor/asunset https://github.com/algoradev/asunset.git main --squash
cp -r vendor/asunset/consuming-template/. .   # first time only
rm -rf consuming-template/                     # no self-reference

# updates, any time — platform migrations ride in automatically
git subtree pull --prefix=vendor/asunset https://github.com/algoradev/asunset.git main --squash
```

- **Whole repo, never a subdirectory** — compose/infra/tools/packages
  reference each other by relative path; a partial vendor breaks silently.
- **Squashed** — your history stays clean; the squash commit records the
  vendored SHA, which is your provenance pin. (No release tags yet:
  `main` is the review-gated contract surface.)
- **Never edit files under `vendor/asunset/`** — additive-only
  customization is what keeps subtree pulls painless (see §5, §8).

## 2. Compose it

**One compose project; your file plays the product-overlay role:**

```sh
docker compose --env-file .env \
  -f vendor/asunset/compose.yml \
  -f vendor/asunset/compose.<mode>.yml \
  -f compose.product.yml \
  up -d
```

Or let the CLI wire everything (recommended — it detects the consumer
layout, includes your overlay, and places `.env` correctly):

```sh
./vendor/asunset/tools/deploy/asunset init     # interactive, or --config … --yes
./vendor/asunset/tools/deploy/asunset up
./vendor/asunset/tools/deploy/asunset doctor   # always after init/up
```

The full operator surface is five verbs: `dev · init · up · doctor ·
upgrade`. `dev` brings up the zero-prompt loopback integration stack
(`http://127.0.0.1:5173`, all secrets generated — it never prompts and
refuses to touch a configured deployment). `upgrade` is the
post-vendor-pull roll (rebuild what bakes, force-recreate
keycloak-init, both doctors) — it **never touches your git**; the
subtree pull stays yours/CI's (§8 has the dirty-tree recipe).

### The product deploy manifest (`product.yaml`)

Declare your deploy contract in `product.yaml` at the consumer root and
the CLI becomes your single door (ruled in the report-95 cycle;
supersedes the older `PRODUCT_COMPOSE` env pointer, which still works
but warns):

```yaml
version: 1
name: your-product
compose: deploy/compose.product.yml   # your overlay
caddyfile:                            # foreign-UI consumers only —
  tailscale: deploy/Caddyfile         # per-mode map; a mode with no
                                      # entry REFUSES at `up`
env:
  generate: [YOURPRODUCT_PG_PASSWORD] # generated into the ONE root .env
                                      # alongside asunset's secrets;
                                      # never rotated on re-init
init: your-init-service               # one-shots the CLI sequences:
doctor: your-doctor-service           # init after infra, doctor gates "ready"
```

The boundary is **infra-only** (ratified doctrine): the manifest may
declare secrets to *generate* and one-shots to *sequence* — never
prompts for product-domain values. Product questions (org names,
instance identity) live in the product, the way asunset's own org is
created by the BootstrapGate, not by `init`. Your one-shots must be
idempotent — `up` re-runs them freely. A failing product doctor leaves
the stack running and reports **partial state** honestly; ruled
pre-adoption warns (auth-enforcement, unstamped, no-store) are named
states, not failures.

**Modes** (`compose.<mode>.yml`): nothing (plain, localhost dev) ·
`tls` (per-hostname HTTPS via Caddy) · `tailscale` (single hostname,
path-routed, tailnet-only). `compose.cohost.yml` is only for the
*separate-project* topology (asunset sharing a host with unrelated
stacks — loopback debug ports); a product deployment is single-project
and doesn't use it.

**Your `compose.product.yml`** (template ships a worked one):
- Disable demo services you replace: `api` (always) and `web` (if you
  ship your own UI) via `profiles: ["donotstart"]`.
- Add your services on the shared network — they reach the platform by
  compose DNS: `http://keycloak:8080` (`/auth` suffix in tailscale
  mode), `http://openfga:8080`, `postgres:5432`.
- Two documented footguns: build contexts in your overlay resolve
  against `vendor/asunset/` (use the `../..` climb-out) and manual
  compose invocations need `--env-file .env`. The CLI handles both.

**Postgres topology (ruled): two postgres services, one project.**
asunset's `postgres` (the service name is platform-owned) carries the
app/keycloak/openfga logical DBs, provisioned by its own init script
with the RLS owner/app role split. If your product has its own
database, it runs as a **separately named** service with a **separate
backup contract** — identity-plane data has a different blast radius,
backup cadence, and compliance posture than product data, and asunset's
DB lifecycle arrives via subtree pull rather than becoming your DB-ops
event. Cost: one extra container. Accepted.

**Images**: built from vendored source; there are no published images.

## 3. Configure it

`asunset init` writes `.env` at your repo root (ten generated secrets
including the agent-session signing key). The env vars every consumer
must understand:

| Var | Rule |
|---|---|
| `KEYCLOAK_PUBLIC_URL` / `KEYCLOAK_INTERNAL_URL` | The split-issuer pattern — public is what browsers see (`iss` claim), internal is where JWKS is fetched. Path-routed modes carry `/auth` on **both**. Get these wrong and every request 401s; `asunset doctor` checks the coherence. |
| `KEYCLOAK_EXTRA_AUDIENCES` | One entry per additional resource server (identity contract D6) — each service validates **its own** entry. |
| `SESSION_TOKEN_PRIVATE_KEY_B64` | Persistent agent-session signing key; generated by init. Empty = ephemeral dev fallback (sessions die on restart; doctor warns). |
| `FEATURES_MANIFEST` / `features_manifest` setting | Path to your feature manifest; empty disables the feature system. |

**After any change to keycloak-init's env or script: force-recreate it
once** (`up -d --force-recreate keycloak-init`) — it's a one-shot
container and will not re-run otherwise. This is the single most
common vendor-bump mistake.

## 4. Build your backend

Your API mounts the platform and adds itself (template's
`product-api/main.py` is the working reference):

- **Models** on the shared SQLAlchemy `Base` — FKs to
  `organization.id`/`team.id`/`app_user.id` just work; RLS extends over
  your tenant tables.
- **Migrations** chain via `platform_head()` — your first migration's
  `down_revision`, so subtree pulls re-anchor automatically. Your
  container's entrypoint runs `alembic upgrade head` on every start
  (idempotent); compose ordering is the template's `depends_on` block
  (postgres healthy, keycloak-init completed, openfga started).
  **Foreign-gate consumers, note the boot-job ownership**: the
  app-level bootstrap — the merged alembic chain (which creates
  `organization` and the platform tables) and `bootstrap_openfga`
  (which creates/pins the FGA store) — belongs to YOUR gate's boot,
  because you profiled out the demo api whose boot normally does it.
  Until your gate wires it (your adoption slice), a co-hosted instance
  legitimately has no `organization` table and no FGA store — those are
  named doctor warn states, not failures, and there is deliberately no
  ops one-shot that creates them early (doctor verifies; boot paths
  mutate).

  > **Amended 2026-07-30 (R1 confirm, thread ef1a190a447b):** the
  > "merged chain via `platform_head()`" language above describes the
  > **shared-Base consumer** (product tables on asunset's Base, same
  > DB — the Notes/centum shape). The **two-DB consumer** (own product
  > postgres, own schema mechanism — the OpsRoom shape) is equally
  > supported and does NOT adopt alembic for its product schema
  > *(this clause SUPERSEDED 2026-08-06 — see the amendment below: a
  > standalone product chain is now the recommended mechanism; the
  > identity-DB and no-anchor clauses of this amendment stand)*: its
  > boot job runs **asunset's own chain** against the **identity DB**
  > (`alembic upgrade head` on the vendored `apps/api/alembic` tree),
  > and the product schema evolves by the product's own mechanism.
> **Amended 2026-08-06 (migrations coordination, thread a99e9ee8b932,
> Avi-called):** "the product's own mechanism" may be — and for any
> product beyond trivial size should be — a **standalone product alembic
> chain** in the product DB, applied by the product's own entrypoint
> (`alembic upgrade head` on boot, the template's flow). The one rule:
> a two-DB consumer's chain **never anchors to `platform_head()`** —
> that helper expresses a same-database dependency and exists for
> shared-Base consumers only; a two-DB chain starts at its own baseline
> revision, with the divergence-from-template justified in the first
> migration's docstring so nobody "fixes" it back. One migrator per
> database (the one-bootstrapper rule applied to schema).
  > Three facts to plan around: (1) `alembic/env.py` imports
  > `asunset_api`, so either install the vendored `apps/api` as a path
  > dep in whatever runs the chain, or run it as a one-shot of the
  > vendored demo-api image (`compose run --rm api alembic upgrade
  > head`) — both supported, consumer's choice; (2) the chain's head
  > currently carries ONE demo table (`note`, created in 0001 — inert,
  > empty, RLS-guarded, only the profiled-out demo api touches it);
  > splitting demo tables out of the platform chain would rewrite
  > shipped migration history, so it stays, named — trigger to revisit:
  > a consumer's compliance table-inventory objects; (3) run the chain
  > with the ADMIN/OWNER DB URL, as the demo api's entrypoint does. Nothing
  else invokes migrations.
- **FGA model**: `build_model([*FEATURE_PLATFORM_TYPES, *YOUR_TYPES])`
  — never redefine `user`/`organization`/`team`; reference them as
  grantee types. One deployment composes **one** model (if several of
  your services contribute types, one owner merges them).
- **The dependency chain is the security property** — depend on
  `get_current_principal → get_current_org → get_db → get_authorizer →
  get_audit_sink`; never reach around it. Never hand-roll JWT
  validation, FGA calls, or audit writes.
- **Non-Python services** validate tokens per
  [`identity-contract.md`](identity-contract.md) §5/§5.1a directly
  (offline JWT: RS256, own audience, iss-selected JWKS). If a
  non-Python service ever needs FGA *decisions*, raise it with the
  platform first — don't improvise a client.

## 5. Build your frontend

Fork `apps/web/` **additively**: new files under `features/<yours>/`,
one edit to `src/config/routes.ts` (`defineConsumerRoutes([...])` wires
routes into sidebar/palette/breadcrumbs/types), i18n strings. The auth
kernel (in-memory tokens, silent renew via the SSO cookie, idle logout,
correlation+bearer fetch) is **imported from `@asunset/web-sdk`** —
`auth.ts` / `api.ts` are thin consumers of it, and your fork keeps them
that way (the old "byte-identical" convention upgraded to structure:
divergence is now inexpressible, not merely forbidden).
Brand/resource strings ride `.env`, not code.
The additive-only rule is what makes upstream pulls and any future
shared-package migration cheap.

### 5b. Ship your own UI — the foreign-UI path

Ruled 2026-07-27 ([`frontend-sdk-decision.md`](frontend-sdk-decision.md)):
you may replace asunset's `web` with a fully independent frontend. Two
obligations come with the freedom:

1. **The auth kernel is not yours to write.** The moment your UI does
   auth against asunset identity, it consumes `@asunset/web-sdk`
   (in-memory tokens, silent renew, idle logout, correlation+bearer
   fetch). Hand-rolled browser OIDC/token handling is a
   **review-blocker** — same class as hand-rolled FGA clients. An
   unauthenticated surface (pre-adoption dev) is compliant; partial or
   parallel auth implementations are not. Wiring guide:
   [`packages/web-sdk/README.md`](../packages/web-sdk/README.md) —
   source-alias install, five wiring steps, the silent-renew page.
   Your SPA's serving layer also owns the CSP/security-header posture
   the in-memory design requires: FastAPI-served SPAs add
   `asunset_core.middleware.SecurityHeadersMiddleware` in the same
   slice (opt-out only with `disabled_reason=`, logged loudly).
2. **The ingress swap uses the sanctioned seam below** — never an edit
   to vendored files.

**The override-mount seam** (supported contract surface). Compose merges
volume mounts by container path — last file wins — so your product
overlay replaces the generated Caddyfile without touching
`vendor/asunset/`. In `compose.product.yml`:

```yaml
services:
  web:
    profiles: ["donotstart"]      # asunset demo UI off

  your-api:                        # serves your SPA same-origin, or a
    build: ...                     # separate SPA service — your shape

  caddy:
    volumes:
      # Relative paths resolve against the PROJECT dir (vendor/asunset/),
      # so climb out — this is your file, at your repo root:
      - ../../deploy/Caddyfile:/etc/caddy/Caddyfile:ro
    depends_on: !override          # REQUIRED — see below
      - keycloak
      - your-api
```

The `depends_on: !override` is not optional: the mode overlays declare
`depends_on: [web, keycloak, api]`, and with `web`/`api` profiled out
compose refuses the project with
`service "caddy" depends on undefined service "web": invalid compose
project` (the centum F1 class). Both behaviors above — mount dedupe by
target and the `!override` reset — are pinned by
`tools/deploy/foreign_ui_recipe_test.go`.

**Your Caddyfile: one block is non-negotiable.** Keycloak runs with
`--http-relative-path=/auth`, and the issuer your API validates is
derived from the public `/auth` URL. Copy this verbatim (path-routed
modes); breaking it kills login platform-wide:

```
handle /auth/* {
    reverse_proxy keycloak:8080
}
```

**Declare your path semantics explicitly.** asunset's demo API serves
*unprefixed* routes, so the generated Caddyfile **strips** `/api`
(`handle_path`). If your API serves routes *under* `/api/*` (OpsRoom's
shape), you must **preserve** the prefix — this is the single easiest
mistake in the swap:

| Your API routes | Caddy directive |
|---|---|
| unprefixed (`/notes`, asunset demo style) | `handle_path /api/* { … }` — strips |
| prefixed (`/api/...`) | `handle /api/* { … }` — preserves |

Worked example — tailscale mode, SPA served same-origin by your API
(replaces the generated `infra/caddy/Caddyfile`):

```
:5173 {
    encode zstd gzip
    handle /auth/* {
        reverse_proxy keycloak:8080
    }
    # SPA + /api/* both live on your service; prefix preserved.
    handle {
        reverse_proxy your-api:8001
    }
    log {
        output stdout
        format console
    }
}
```

**TLS modes**: the three-vhost split collapses for a same-origin SPA —
point both the web-host and api-host blocks at your service (or drop the
api vhost and serve everything on one host; then `TLS_API_HOST` names
your single ingress host). Keep the `{AuthHost}` block exactly as
generated. Keep the security headers (`Strict-Transport-Security`,
`X-Content-Type-Options`, `Referrer-Policy`, `-Server`) from the
generated templates — you own reproducing that posture now; diff your
Caddyfile against the generated one on every vendor bump.

**Verify after every change**: `asunset doctor` probes the caddy edge
(`edge-auth-route`) to confirm `/auth` still answers with the configured
realm's discovery document through the front door — the recipe's
non-negotiable, checked live.

**API error contract:** structured error codes, never message-string
matching. Error responses that UIs must branch on carry
`{"detail": {"code": "...", "message": "..."}}`; the web-sdk surfaces
`code` on `ApiError`. Matching on message text is a review flag — the
same brittleness class twice caught in the field (the invite dialog's
already-a-member match; the deck resolution seam).

## 6. Features, roles, sessions

- **Feature permissions** — declare in `features.yaml`, gate with
  `require_feature(Feature.X)`, guard UI with `useFeatures()`. Full
  recipe: [`adding-a-feature.md`](adding-a-feature.md) · system + v1.1
  runtime grants/freeze + §11 capability model:
  [`feature-permissions-spec.md`](feature-permissions-spec.md) ·
  design ceremony: [`feature-decision-template.md`](feature-decision-template.md).
  Scaffold: `python -m asunset_core.features.scaffold`. **Never mint
  product realm roles for feature gating** (superseded) and **never
  hand-write FGA tuples** — runtime grants go through the audited
  `/platform/features/*` and `/platform/roles/*` APIs.
- **Agent sessions** — scoped, attributable, instantly revocable:
  [`session-token-mint-spec.md`](session-token-mint-spec.md). `sub` is
  always the human; agents are never service accounts.
- **Testing** — `asunset_core.testing`: `StaticAuthorizer` for fast
  endpoint tests, `async with ephemeral_openfga(YOUR_MODEL)` for model
  semantics (async context manager — drive the whole session under one
  `asyncio.run`);
  the route-test skeleton is in the recipe; matrix skeletons generate
  via `python -m asunset_core.features.matrix`.

## 7. Operate it

- **`asunset doctor`** (`--json`) — run after every init, up, and
  vendor bump: env coherence + live probes (readiness breakdown,
  issuer advertised-vs-configured, session JWKS, feature drift via the
  machine operator identity).
- **Incidents**: [`runbooks/feature-freeze.md`](runbooks/feature-freeze.md)
  — freeze is reversible and grant-preserving; `enabled: false` in the
  manifest is decommission (destructive sweep). Distinct tools.
- **Tokens for ops**: [`runbooks/operator-token.md`](runbooks/operator-token.md)
  — machine path (client credentials, `platform_support`) vs human
  admin path, with the MFA cliffs named.
- **Compliance**: `GET /platform/features/matrix` (dated live matrix
  with provenance) · `GET /platform/features/{key}/explain?user_id=`
  ("why does X (not) have this") · the audit trail is append-only and
  SIEM-shipped by construction.

## 8. Vendor-bump runbook

```sh
git subtree pull --prefix=vendor/asunset https://github.com/algoradev/asunset.git main --squash
# rebuild what bakes: web (URLs bake at build time), your api, keycloak-init
docker compose … build web keycloak-init <your-api>
docker compose … up -d --force-recreate keycloak-init
./vendor/asunset/tools/deploy/asunset doctor
```

Migrations apply on your api's next start (`platform_head()` re-chains
your product migration automatically). If the pull conflicts in
`vendor/asunset/`, you edited vendored files — resolve toward upstream
and move your change out (additive-only).

## Known consumer history

Real friction reports from real consumer runs live in
[`friction/`](friction/) — read them before assuming a paper cut is
yours alone. The consuming-template's README carries the deeper
walkthrough of the product-api skeleton itself.

# consuming-template

Reference boilerplate for a product built on asunset. Copy this directory
into a new private repo, subtree the asunset core as `vendor/asunset/`,
customize the resource type, and ship.

## What you get by depending on asunset

Every product built on top of asunset automatically inherits:

- **Identity** (Keycloak) — single sign-on, MFA on privileged accounts,
  the realm's audit events piped into the same SIEM stream
- **Authorization** (OpenFGA) — ReBAC model with platform types
  (`user`, `organization`, `team`) already defined; your product appends
  its resource types
- **Audit pipeline** — `AuditSink` with identity snapshot, correlation
  ID, permission path, forensic triple (source IP / user-agent /
  session ID), append-only at the DB layer, Vector shipping
- **RLS-scoped sessions** — `get_db()` yields a Postgres session with
  `app.current_user_id` and `app.current_org_id` set per request
- **Platform HTTP surface** — orgs, teams, users, audit, /platform
  routers mounted from `asunset_api` onto your FastAPI app
- **Deploy wizard** — `./vendor/asunset/tools/deploy/asunset-deploy`
  generates `.env` + Caddy config for five deployment modes

Your product code only needs to define:
1. A SQLAlchemy model on the shared `Base`
2. An OpenFGA type definition
3. A FastAPI router for CRUD on your resource
4. Audit-event emission for every mutation (using the shared `AuditSink`)

## Setup in your product repo

```sh
# One-time
git init
git remote add origin git@github.com:you/my-product.git

# Vendor asunset
git subtree add --prefix=vendor/asunset git@github.com:you/asunset.git main --squash

# Copy this scaffold
cp -r vendor/asunset/consuming-template/. .
rm -rf consuming-template/  # no self-reference

# Install deps (uses uv — adapt if you prefer pip)
uv sync

# Deploy wizard
./vendor/asunset/tools/deploy/asunset-deploy
```

## Updating asunset

```sh
git subtree pull --prefix=vendor/asunset git@github.com:you/asunset.git main --squash
```

Conflicts are the same as any `git merge`. Your product code lives
OUTSIDE `vendor/asunset/` so routine asunset updates never touch it.

## Layout

```
.
├── compose.product.yml         # overlay: adds product-api service to the asunset stack
├── vendor/
│   └── asunset/                # subtree — DO NOT edit unless you mean to fork
│       ├── compose.yml         #   asunset's base stack
│       ├── compose.tailscale.yml
│       ├── packages/asunset_core/
│       ├── apps/api/           #   the Notes demo (won't run in consumer deployments)
│       ├── apps/web/           #   demo UI — fork into your own apps/web/ if desired
│       └── tools/deploy/       #   deployment wizard, built at `./asunset-deploy`
├── apps/
│   └── product-api/            # YOUR product backend
│       ├── pyproject.toml
│       ├── Dockerfile
│       ├── alembic.ini
│       ├── alembic/versions/
│       └── src/product_api/
│           ├── main.py         # mounts platform routers + product router
│           ├── config.py
│           ├── models.py       # Report (your resource) on the shared Base
│           ├── fga_model.py    # product's FGA model = platform types + Report
│           ├── router.py       # Report CRUD + share + audit
│           └── schemas.py
└── infra/
    └── fga-extension.fga       # human-readable DSL mirror of fga_model.py
```

## How to deploy

```sh
docker compose \
  -f vendor/asunset/compose.yml \
  -f vendor/asunset/compose.tailscale.yml \
  -f compose.product.yml \
  up -d
```

The overlay replaces asunset's demo `api` service with your
`product-api`. Keycloak, OpenFGA, Postgres, Caddy, Vector all stay as
they are — that's the platform plumbing you're building on.

## Extension points — what to edit

### 1. Your resource (`models.py`)

Inherits from `asunset_core.db.Base`. FKs to `organization.id`,
`team.id`, `app_user.id` work because all platform tables are on the
same metadata graph.

### 2. Your FGA model (`fga_model.py`)

Use `asunset_core.build_model([YOUR_TYPE_DEFINITIONS])` to merge your
types with the platform baseline. `bootstrap_openfga()` pins the
returned model ID.

### 3. Your router (`router.py`)

Uses the same dependency injection pattern as asunset:
- `principal: Principal = Depends(get_current_principal)` — JWT validated
- `authorizer: Authorizer = Depends(get_authorizer)` — OpenFGA client
- `audit: AuditSink = Depends(get_audit_sink)` — correlated + enriched
- `session: AsyncSession = Depends(get_db)` — RLS-scoped
- `org: OrgContext = Depends(get_current_org)` — caller's org context

### 4. Your Alembic (`alembic/versions/`)

First migration's `down_revision` points to asunset's last migration
(`"0004"` at the time of writing). Your migration only creates YOUR
tables. Run `alembic upgrade head` and both platform + product tables
materialize in order.

### 5. Your compose overlay (`compose.product.yml`)

Declares the `product-api` service, wires it to Postgres/OpenFGA/Keycloak
the same way asunset's demo api does. Routes under `/reports`, `/orgs`,
`/teams`, `/audit`, etc.

## What NOT to put in your product

- **Don't reimplement JWT validation.** Import `get_current_principal`.
- **Don't reimplement FGA calls.** Use the `Authorizer` port.
- **Don't write to `audit_event` directly.** Use `AuditSink.emit()` so
  identity/IP/session get snapshotted correctly.
- **Don't skip correlation IDs.** `CorrelationIdMiddleware` is mounted
  automatically; the logger and audit sink both read from it.
- **Don't define your own `organization`, `team`, `user`, or member
  types in FGA.** They come from `PLATFORM_TYPES`.

## Working example: the Notes demo

The asunset repo itself ships the same pattern as the Notes demo in
`vendor/asunset/apps/api/`. If you're stuck, read that directory as
your working reference — it's the "Hello World" of asunset consumption.

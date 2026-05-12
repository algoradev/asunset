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
# Make sure your tree is clean first — subtree pull lands a merge commit.
git status

# Pull in upstream changes.
git subtree pull --prefix=vendor/asunset git@github.com:you/asunset.git main --squash

# Or use the helper that hardcodes the prefix (only the upstream URL changes):
./scripts/update-vendor.sh git@github.com:you/asunset.git
```

Conflicts are the same as any `git merge`. Your product code lives
OUTSIDE `vendor/asunset/` so routine asunset updates never touch it.

**Expect to re-port `apps/web/` after a major UI overhaul.** If you
forked `apps/web/` and edited `App.tsx` / `app-sidebar.tsx` / etc., a
breaking upstream change (sidebar rewrite, router refactor, theme
migration) means your customizations are layered on top of files that
no longer exist. The merge will succeed at the file level but won't
*integrate*; cleanest path is to re-port your feature pages onto the
new shell. Pulling upstream **frequently** keeps each delta small —
big bang merges are what hurt. Keep customizations additive (new
files good, edits to vendored files bad) so the re-port surface stays
small. The B3-style `CONSUMER_ROUTES` extension point in the asunset
shell is designed exactly to shrink that surface.

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

The recommended path is the bundled `asunset` CLI — it auto-detects
the consumer layout (your `vendor/asunset/` subtree + the sibling
`compose.product.yml`) and wires every flag for you:

```sh
# One-time interactive setup. Run from your consumer repo root.
./vendor/asunset/tools/deploy/asunset init

# Lifecycle commands. All read ASUNSET_MODE from .env and pick the
# right overlays automatically — including your compose.product.yml.
./vendor/asunset/tools/deploy/asunset up
./vendor/asunset/tools/deploy/asunset logs api
./vendor/asunset/tools/deploy/asunset down
```

`asunset init` writes `.env` at the consumer root (next to your
`compose.product.yml`), not inside `vendor/asunset/`. `asunset up`
auto-includes the product overlay if it exists; you don't pass `-f`
flags. The Caddyfile (TLS modes only) lands at
`vendor/asunset/infra/caddy/Caddyfile` because that's where asunset's
compose mounts it from.

### Manual fallback (if you can't or don't want to use the CLI)

```sh
docker compose --env-file .env \
  -f vendor/asunset/compose.yml \
  -f vendor/asunset/compose.tailscale.yml \
  -f compose.product.yml \
  up -d
```

The overlay replaces asunset's demo `api` service with your
`product-api`. Keycloak, OpenFGA, Postgres, Caddy, Vector all stay as
they are — that's the platform plumbing you're building on.

**Why `--env-file .env` is required for the manual form.** With
multiple `-f` files Compose sets the *project directory* to the
directory of the first `-f` — `vendor/asunset/` in this case. It then
auto-discovers `.env` from *that* directory, not from your consumer
root. Without the explicit flag every env var expands to an empty
string and Compose blames it on the wrong service ("web depends on
undefined service api"). Same goes for any relative path in your
`compose.product.yml`: it resolves against `vendor/asunset/`, not
against the file's own location — see the comment block at the top of
`compose.product.yml` for the climb-out trick (`context: ../..`). The
CLI handles all of this for you.

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

Your first migration should anchor to asunset's platform head via the
`platform_head()` helper:

```python
from asunset_core.alembic_helpers import platform_head

revision: str = "1000"
down_revision: str | None = platform_head()
```

This way every `git subtree pull` of `vendor/asunset/` automatically
picks up whatever the new platform head is — you don't bump a literal
revision id by hand, and you can't silently chain to a stale revision
(which produces an opaque "Multiple head revisions are present" error
on the next deploy). Your migration only creates YOUR tables. Run
`alembic upgrade head` and both platform + product tables materialize
in order. The example migration in this scaffold uses the helper.

### 5. Your compose overlay (`compose.product.yml`)

Declares the `product-api` service, wires it to Postgres/OpenFGA/Keycloak
the same way asunset's demo api does. Routes under `/reports`, `/orgs`,
`/teams`, `/audit`, etc.

## Email

Two independent layers, deliberately kept separate so each can be
swapped or disabled without touching the other.

### Keycloak SMTP (auth flows)

Drives Keycloak's own emails — verify-email, forgot-password, the
magic-link sent when `requiredActions=["UPDATE_PASSWORD"]` is set on
an invited user. Configured at the realm level by `keycloak-init`
from `KC_SMTP_*` env vars; leave `KC_SMTP_HOST` empty to disable
Keycloak email entirely (the default for local dev).

Resend example:

```
KC_SMTP_HOST=smtp.resend.com
KC_SMTP_PORT=587
KC_SMTP_USER=resend
KC_SMTP_PASSWORD=<your Resend API key>
KC_SMTP_FROM=noreply-auth@your-domain.com
KC_SMTP_STARTTLS=true
KC_SMTP_AUTH=true
```

### Onboarding without SMTP (Linode et al.)

Some hosts (Linode, Hetzner Cloud, AWS without verified SES) block
outbound SMTP entirely. Keycloak's magic-link invite path is a
non-starter on those hosts. Set:

```
INVITE_DELIVERY=temp_password
```

The invite endpoint then generates a strong one-time password, sets
it on the new Keycloak user with `temporary=true`, and returns it in
the API response. The admin sees it in a one-time copyable callout
in the Invite dialog, conveys it out-of-band (Signal, in person,
secure chat), and the new user signs in once — Keycloak immediately
forces them to set their own password, then redirects them into the
app already a member.

`INVITE_DELIVERY=auto` tries the magic-link path first and falls back
to a temp password if Keycloak's email errors. Useful on hosts where
SMTP "should" work but you want resilience against transient outages.

`INVITE_DELIVERY=magic_link` is the default and matches the original
behavior — requires `KC_SMTP_HOST` and a reachable SMTP gateway.

The mode is read from env at request time, so swapping it doesn't
require a rebuild — just `asunset restart api` after editing `.env`.

### App-side notifier (product flows)

A `Notifier` port in `asunset_core.notifications` with two adapters
out of the box:

- `LogNotifier` — logs every send to stdout, no network. Default
  (`NOTIFIER_BACKEND=log`) so a fresh checkout never sends real mail.
- `ResendNotifier` — posts to Resend's HTTP API. Activate with
  `NOTIFIER_BACKEND=resend` + `RESEND_API_KEY=...`.

Routes inject `EmailService` via FastAPI's `Depends(get_email_service)`
and call `await email.send(template="welcome", locale=user.locale,
to=user.email, context={...})`. The service composes rendering and
delivery; you don't see the Notifier directly.

Templates are Jinja2 trios — `<name>.subject.txt`, `<name>.html`,
`<name>.txt` — under `templates/<locale>/`. Asunset ships `welcome`
and `org_member_added` in `en` + `es`; the renderer falls back to
`en` for any locale where a key is missing. To add your own
templates, point `NOTIFIER_TEMPLATE_DIR` at a directory of overrides
— it's searched *before* the bundled defaults, so you can replace a
single template without copying the whole set.

Sender identity is intentionally different from Keycloak's:
`NOTIFIER_DEFAULT_SENDER=noreply@<your-domain>` for the app vs
`KC_SMTP_FROM=noreply-auth@<your-domain>` for Keycloak. Operators
running both providers through Resend should configure each as a
distinct sending identity in Resend.

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

## Forking the web app

The first 1–2 consumer products fork `apps/web/` outright — no shared
UI library yet. When a second consumer starts showing the same UI
patterns as the first, that's the signal to extract `@asunset/react`.
Until then, a fork is faster to rebrand and gives full styling autonomy.

### Bootstrap

```sh
cp -r vendor/asunset/apps/web/. apps/web/
cd apps/web
npm install
```

You now own `apps/web/`. Upstream improvements come through
`git subtree pull` into `vendor/asunset/`; you cherry-pick what you
want out of `vendor/asunset/apps/web/` and apply it to your fork.

### Rebranding: env vars first, code second

Most brand strings live in env so rebrands ride along with `.env` and
don't churn vendored TypeScript on every upstream pull. Set the
following in your consumer-root `.env` (compose forwards them to the
web container as build args + runtime env):

```
VITE_BRAND_NAME=Centum
VITE_RESOURCE_NAME=Transaction
VITE_RESOURCE_PLURAL=Transactions
VITE_RESOURCE_NEW_LABEL=New transaction
VITE_RESOURCE_EMPTY_LABEL=No transactions in this view.
VITE_RESOURCE_SHARE_DESC=Grant access to a user, a team, or the whole org.
```

That covers the sidebar header, breadcrumb, browser tab title (via
Vite's `%VITE_BRAND_NAME%` token substitution in `index.html`), and
the resource labels rendered across the demo pages. No code changes
needed for these.

**Two fields stay in code** because they can't come from string env:

- `apps/web/src/config/resource.ts` → `routeKey` drives the `Route`
  type union and the URL hash; must be a literal string.
- `apps/web/src/config/resource.ts` → `icon` is a Lucide React
  component, not a string.

```ts
// src/config/resource.ts in a Reports fork — the only edits left
import { BarChart3 } from "lucide-react";
export const RESOURCE = {
  routeKey: "reports",
  icon: BarChart3,
  // name, plural, newLabel, emptyLabel, shareDialogDescription
  // come from env — leave the defaults here untouched.
  ...
} as const;
```

**Multiple environments, one image.** Because the brand surface is
env-driven, a single built image can serve dev / staging / prod with
different `VITE_BRAND_NAME` values — no per-environment fork.

### Adding secondary routes (`src/config/routes.ts`)

Beyond the primary `RESOURCE`, products usually have several read-only
auxiliary surfaces — KPI dashboards, deposits, balances, log views.
Don't edit the sidebar, command palette, App.tsx, route.ts, and both
i18n locales by hand for each one. Use `CONSUMER_ROUTES`:

```ts
// apps/web/src/config/routes.ts (overrides the empty default in vendored asunset)
import { Landmark, LineChart, Wallet } from "lucide-react";
import { defineConsumerRoutes } from "@/config/routes";
import { DepositsPage } from "@/features/deposits/DepositsPage";
import { KpiPage } from "@/features/kpi/KpiPage";
import { BalancePage } from "@/features/balance/BalancePage";

export const CONSUMER_ROUTES = defineConsumerRoutes([
  { key: "deposits", labelKey: "nav.deposits", paletteLabelKey: "palette.gotoDeposits", icon: Landmark, page: <DepositsPage /> },
  { key: "kpi",      labelKey: "nav.kpi",      paletteLabelKey: "palette.gotoKpi",      icon: LineChart, page: <KpiPage /> },
  { key: "balance",  labelKey: "nav.balance",  paletteLabelKey: "palette.gotoBalance",  icon: Wallet,   page: <BalancePage />, visible: ({ orgRole }) => orgRole === "admin" },
]);
```

That single file extends the `Route` type union, the sidebar `NavMain`,
the command palette nav group, and the breadcrumb `pageTitle`. The
optional `visible` predicate hides a route from the sidebar/palette
when the predicate returns false. `defineConsumerRoutes(...)` is a
pass-through helper that preserves the literal key types so
`navigate("deposits")` is type-checked.

You still own the i18n strings: add `nav.deposits` /
`palette.gotoDeposits` / etc. to every locale you support.

### What's config vs. what you rewrite

| Owned by config           | Owned by consumer code                                 |
| ------------------------- | ------------------------------------------------------ |
| Product name, sign-in     | Domain schema (title/body fields in your "New" dialog) |
| Resource name & plural    | Validation rules for your resource                     |
| Resource URL hash         | Access-path badge vocabulary if your model differs     |
| Sidebar label & icon      | Any resource-specific filter or sort                   |
| Share-dialog description  | Extra feature pages unique to your product             |

Rule of thumb: if the string changes with the rebrand but the UI
structure stays the same, it belongs in config. If the column set
changes, it's code — edit the relevant `features/<resource>/*.tsx`.

### Shared UI you inherit

- **`components/States.tsx`** — `LoadingState`, `ErrorState`,
  `EmptyState`. Use these instead of inline `<p class="…">` so
  behavior stays consistent.
- **`sonner` Toaster** — mounted at the root (`main.tsx`). Every
  mutation fires `toast.success` / `toast.error` instead of rendering
  inline error text. Queries still use `<ErrorState>` because their
  failures are persistent, not transient.
- **Idle auto-logout** — HIPAA-aligned 15min idle + 1min warning,
  tied to Keycloak's SSO idle timeout. Don't remove.

### Keep JWT + correlation invariants

The backend doesn't care which frontend you ship. It only needs:
- `Authorization: Bearer <keycloak-jwt>` on every API call.
- `X-Correlation-Id` header per request (middleware adds one if missing).
- OIDC auth-code + PKCE flow.

If your fork preserves `api.ts` and `auth.ts`, you inherit all three.

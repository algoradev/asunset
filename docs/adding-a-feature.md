# Adding a feature: the copy-pastable recipe

The end-to-end mechanics of shipping one gated feature, with exact
commands and snippets. Written from caliper's exercise-1 friction report
(2026-07-26): the concepts live in `docs/feature-permissions-spec.md`
and the narrative in `docs/feature-cycle-story.md`; **this file is the
part you paste**. Example feature throughout: `notes.export`.

Before you type anything: decide *who gets it* (the decision record +
access matrix from the story). This recipe assumes that's done.

## 1. Declare it — `features.yaml`

```yaml
# apps/<your-api>/features.yaml   (schema modeline at the top of the file
# gives you editor validation — keep it)
features:
  notes.export:
    description: "Download the caller's visible notes as CSV"
    grants:
      - organization#member    # or [] for the runtime-only pattern
```

## 2. Generate the typed constants

```sh
cd apps/api   # your api package root, where features.yaml lives
uv run python -m asunset_core.features.codegen features.yaml \
  --py src/asunset_api/features_gen.py \
  --ts ../web/src/config/features.gen.ts
```

This emits `Feature.NOTES_EXPORT` (Python `StrEnum`) and adds
`"notes.export"` to the frontend `FeatureKey` union. Never hand-edit
generated files.

## 3. Gate the endpoint

```python
from asunset_api.features_gen import Feature
from asunset_api.routers.deps import require_feature

@router.get("/export", dependencies=[Depends(require_feature(Feature.NOTES_EXPORT))])
async def export_notes(...):
    ...
```

Notes that save you a guess:

- **A typo'd key fails the boot** (gate-key validation), so if the app
  starts, the gate is real.
- **Feature ∧ resource compose by stacking**: `require_feature` answers
  "may they use this capability at all"; per-object access stays the
  resource check's job. Don't fold one into the other.
- **`list_objects(user, "can_view", "note")` already includes owned
  notes** — ownership derives `can_view` through the FGA model, so you
  do NOT need to union owner rows in manually.

## 4. Gate the UI

```tsx
import { useFeatures } from "@/lib/useFeatures";

const { has } = useFeatures();
...
{has("notes.export") && <Button onClick={exportCsv}>Export CSV</Button>}
```

`has()` is typed against the generated union — a typo'd key is a
compile error. Hide gated chrome while features load; don't flash it
and 403. The UI gate is UX only — the API check is the control.

## 5. Test it — the route-test skeleton

The consumer testing kit (`asunset_core.testing`) supplies the
authorizer; the rest of the skeleton overrides the platform deps so no
database, Keycloak, or OpenFGA is needed:

```python
# tests/test_notes_export.py — complete, runnable shape
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from asunset_core.auth.oidc import get_current_principal
from asunset_core.auth.principal import Principal
from asunset_core.testing import StaticAuthorizer, grant_feature
from asunset_api.routers import deps, notes


def make_app(authz: StaticAuthorizer, principal: Principal) -> FastAPI:
    app = FastAPI()
    app.include_router(notes.router)
    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[deps.get_authorizer] = lambda: authz
    # Override the DB/org/audit deps with fakes appropriate to your
    # endpoint (an object with .execute(...) for get_db; a recorder with
    # an async .emit(...) for get_audit_sink; a stub OrgContext for
    # get_current_org). Only override what the route actually touches.
    return app


async def test_denied_without_feature():
    p = Principal(user_id=uuid4(), email="u@t", display_name="U")
    app = make_app(StaticAuthorizer(), p)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/notes/export")).status_code == 403


async def test_allowed_with_feature():
    p = Principal(user_id=uuid4(), email="u@t", display_name="U")
    authz = StaticAuthorizer()
    grant_feature(authz, p.fga_user(), "notes.export")
    app = make_app(authz, p)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/notes/export")).status_code == 200
```

Plus the staleness guard (copy verbatim, adjust paths):

```python
from asunset_core.features.codegen import assert_generated_current

def test_feature_codegen_current():
    assert_generated_current("features.yaml",
                             py_path="src/asunset_api/features_gen.py",
                             ts_path="../web/src/config/features.gen.ts")
```

Run yours without booting the platform's container suites:

```sh
cd apps/api && uv run --extra dev pytest tests/test_notes_export.py -q
cd ../web && npx tsc --noEmit
```

For tests of *model semantics* (userset derivations, role inheritance)
use the real thing: `asunset_core.testing.ephemeral_openfga(YOUR_MODEL)`
— one disposable container, session-scoped.

## 6. Ship & scope

Deploy runs reconcile automatically (startup + after bootstrap); apply
manifest edits to a running instance with
`POST /platform/features/reconcile` (platform_admin; `dry_run: true`
previews). Runtime grants (roles, teams, users) are the v1.1 surface —
until it lands, features needing them wait; hand-writing FGA tuples is
never the interim.

## The whole loop, one screen

```
edit features.yaml  →  codegen  →  gate endpoint (Feature.X)
      →  gate UI (has("x"))  →  tests (kit + staleness)  →  deploy/reconcile
```

# Consumer DX Exercise: notes.export

Agent: caliper
Branch: caliper/notes-export-consumer-dx
Date: 2026-07-25

## Timeline

- 5 min: Read assignment, created branch from current `main`, checked allowed documentation boundary.
- 20 min: Read `README.md`, `docs/feature-permissions-spec.md`, `docs/feature-cycle-story.md`, `consuming-template/README.md`, `consuming-template/features.yaml`, then public docstrings for `asunset_core.testing` and `asunset_core.features.codegen`.
- 35 min: Added `notes.export` to `apps/api/features.yaml`, ran codegen, added the backend CSV route, wired the frontend API client and gated button.
- 40 min: Wrote isolated consumer-style tests with `StaticAuthorizer` and `assert_generated_current`; first test run failed on app settings import, then I narrowed the test app to the Notes router.
- 15 min: Ran requested backend tests and web typecheck, did a targeted Ruff import cleanup, reran verification.
- 20 min: Wrote this report and reviewed the final diff.

## Friction Points

1. `README.md` says `apps/api/` and `apps/web/` are "read-as-reference only" for consumers, but the exercise asks me to edit the Notes demo in place. For the exercise this is fine, but for a zero-context developer the consumer boundary is contradictory.

2. The feature docs describe the system but not the exact in-repo command for the demo. The codegen docstring gives a generic command:

   ```sh
   python -m asunset_core.features.codegen features.yaml --py src/product_api/features_gen.py --ts apps/web/src/config/features.gen.ts
   ```

   I guessed the local command:

   ```sh
   uv run --project apps/api --extra dev python -m asunset_core.features.codegen apps/api/features.yaml --py apps/api/src/asunset_api/features_gen.py --ts apps/web/src/config/features.gen.ts
   ```

3. "Caller visible notes" is not defined for export. I guessed it means owned notes plus `authorizer.list_objects(user, "can_view", "note")`, deduped by SQL and ordered by `created_at, id`. The existing list endpoint has scope-specific logic, but no reusable "all visible notes" helper.

4. The docs say "gate endpoints" and show `require_feature("reports.export")`, but the generated enum usage was only obvious after reading source (`audit.py` uses `Feature.AUDIT_VIEW`). Good pattern, under-documented recipe.

5. Frontend docs say `useFeatures()` but not the exact import path or how to wire a non-JSON API response through the existing API client. I had to read `apps/web/src/lib/useFeatures.ts`, `apps/web/src/api.ts`, `PageHeader`, and `NotesPage` to infer the idiom.

6. The consumer testing kit docstring is useful, but it does not show a complete FastAPI route test with dependency overrides. My first attempt imported `asunset_api.main.create_app`; collection failed with eight missing settings:

   ```text
   app_db_url, app_admin_db_url, keycloak_issuer,
   keycloak_internal_issuer, keycloak_api_client_id,
   keycloak_api_client_secret, openfga_api_url, openfga_api_key
   ```

   I guessed the right consumer-test shape is a tiny `FastAPI()` app with only `notes.router` mounted, plus overrides for principal, authorizer, DB, and audit.

7. To build tests without reading platform tests, I still had to inspect source for `Principal`, `Authorizer`, and `AuditSink` signatures. The docstrings tell the concept; the exact constructor/override shapes are not in the feature docs.

8. Running a targeted Ruff check on touched Python files surfaced many existing `B008` warnings in `notes.py` for FastAPI `Depends(...)` defaults. That was noisy because the project already uses that FastAPI idiom. I only fixed import sorting.

9. `feature-cycle-story.md` says the build is short and typoed gates fail boot with the mismatch named. That promise seems true in source, but the story does not tell a consumer how to run the gate-validation path locally or how it relates to the staleness test.

## Guesses Made

- Export includes all visible notes, not just the currently selected UI tab.
- Owner visibility remains DB-authoritative like `scope=mine`; non-owned visibility comes from FGA `can_view`.
- CSV dates should use `datetime.isoformat()` to match API JSON style.
- A hidden button is the right denied-feature UX; no disabled/locked state for a normal missing feature.
- Tests should live outside `apps/api/tests` to avoid platform-suite fixtures and keep the run scoped to my files.

## Source-Discovered Details

- Backend generated constants live in `apps/api/src/asunset_api/features_gen.py`.
- Frontend generated union lives in `apps/web/src/config/features.gen.ts`.
- `require_feature` accepts generated str-enums and normalizes `.value`.
- Existing reference feature gate is `audit.view` in `routers/audit.py`.
- `useFeatures().has` is typed as `has(key: FeatureKey)`.
- The API client only handled JSON before this change, so CSV needed a text request helper.
- `asunset_api.main` constructs `app` at import time, so importing it in tests needs full settings unless the test avoids that module.

## What Was Good

- The manifest shape and default userset grant model were clear.
- The "features are permissions, not token claims or Keycloak roles" rule is unambiguous.
- The generated frontend union made the UI gate typo-safe.
- `StaticAuthorizer`, `grant_feature`, and `assert_generated_current` are the right primitives and were enough once I knew how to wrap a small FastAPI app.
- Existing source patterns were consistent once found: audit feature gate, `useFeatures`, and API client structure all lined up.

## Verification

- `uv run --extra dev pytest consumer_dx_tests/test_notes_export.py -q`: 3 passed.
- `npx tsc --noEmit`: clean.
- No `apps/web/vite.config.js` or `apps/web/vite.config.d.ts` artifacts were emitted.

## Verdict

A competent developer with zero asunset context can ship a simple cycle-A manifest-default feature in the promised "a day per surface", but not yet from documentation alone. The backend and frontend patterns are solid; the missing piece is a single copy-pastable consumer recipe.

Single highest-impact change: add an end-to-end "Add a feature to Notes" recipe with exact codegen command, enum imports, backend gate snippet, frontend `useFeatures` snippet, isolated FastAPI test skeleton, and codegen-staleness test.

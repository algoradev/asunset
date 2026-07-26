# Exercise 3 Friction Report: notes.share Capability Model

Agent: caliper  
Branch: `caliper/exercise3-capability-model`  
Date: 2026-07-26  
Scope: docs-only exploration plus the requested consumer implementation/probes/live operation.

## Outcome

Implemented `notes.share` as a capability area with closed modes:

- `notes.share.basic`: default `organization#member`, reach `note -> shareable_notes`
- `notes.share.org_wide`: default `role:sharers#assignee`, reach `note -> shareable_notes`

The app now has a registered `shareable_notes` resolver based on `can_delete`,
generated constants/grouping artifacts, regenerated design-time matrix rows,
and filled matrix-row evidence for both new capabilities. I added one
org-wide stub endpoint, `GET /notes/share/org-wide/candidates`, gated by
`notes.share.org_wide` and using `resolve_scope` as the sole note data door.

## Timeline

- Read spec section 11, the feature decision template, the adding-a-feature
  recipe, current matrix, scaffold help, scope/matrix module docstrings, and
  the shipped feature-matrix skeleton tests.
- Filled `docs/feature-decision-notes-share.md` before modifying the manifest.
- Declared `areas.notes.share.modes: [basic, org_wide]` plus both feature rows
  in `apps/api/features.yaml`.
- Ran scaffold for `notes.share.basic` and `notes.share.org_wide` to compare the
  generated ceremony with the intended area.
- Added `shareable_notes`, made local scope registration idempotent, added the
  org-wide stub endpoint, and regenerated constants/matrix/skeletons.
- Filled the two new skeleton files with gate evidence and resolver evidence.
- Ran the required negative probes and restored the good manifest after each.
- Rebuilt the smoke API, operated reconcile/role/explain/matrix endpoints, and
  rebuilt once more after a final endpoint guard so the live container matched
  source.

## Source Attribution

| Step | What was clear from docs | What came from OpenAPI | What was a guess/inference |
|---|---|---|---|
| Decision record | Spec section 11 and `docs/feature-decision-template.md` made the area/capability distinction and decision-first flow clear. | N/A | The concrete filename was inferred because no decision-record directory exists. I used `docs/feature-decision-notes-share.md`. |
| Manifest shape | Scaffold output and spec section 11 showed `areas:`, closed `modes`, `features:`, grants, and `scope` pairs. | N/A | Scaffold emits a one-mode area per command; combining `basic` and `org_wide` into one area was manual. |
| Resolver choice | Scope docstrings/spec say resolvers are narrow-only and lifecycle-blind, and are referenced by registered name. | N/A | `visible_notes` did not fit share authority. I inferred `shareable_notes` should follow the Notes app's existing share gate, `can_delete`, from the router business logic. |
| Stub endpoint | Scaffold showed `require_feature(Feature...)` plus `resolve_scope(...)` as the sole-data-door pattern. | OpenAPI confirmed `/notes/share/org-wide/candidates` after rebuild. | Response shape was not prescribed. I returned hydrated `NoteOut` rows for resolver-admitted ids only. |
| Regeneration | `asunset_core.features.codegen --help`, `asunset_core.features.matrix --help`, and docs gave the commands. | N/A | The package-relative skeleton path is `apps/api/tests/feature_matrix`, not repo-root `tests/feature_matrix`. |
| Live operation | Runtime grants docs from prior exercise and feature router behavior made reconcile/roles/explain intent clear. | OpenAPI confirmed `/platform/features/reconcile`, `/platform/roles/{role}/assignees`, `/platform/features/{key}/explain`, and `/platform/features/matrix`. | Startup reconciliation auto-applied the new defaults before manual preview/apply, so the explicit preview/apply was idempotent. |

## Frictions

1. **CLI codegen broke as soon as an area existed.**  
   Running codegen after adding `areas:` failed with:

   ```text
   NameError: name 'areas_python' is not defined
   ```

   Cause: `if __name__ == "__main__": main()` appeared before `areas_python`,
   but `python_module()` calls `areas_python()` when the manifest has areas.
   I moved the CLI entrypoint to the bottom of `codegen.py`.

2. **Scaffold helps but does not compose multi-mode areas.**  
   The two scaffold runs separately produced:

   ```yaml
   areas:
     notes.share:
       modes: [basic]
   ```

   and:

   ```yaml
   areas:
     notes.share:
       modes: [org_wide]
   ```

   For a real area, the user still has to manually merge those into
   `modes: [basic, org_wide]`.

3. **The prompt path and repo path differed for skeletons.**  
   The prompt named `tests/feature_matrix/`, but the shipped app tests are in
   `apps/api/tests/feature_matrix/`. The matrix CLI worked once run from
   `apps/api` with `--skeletons tests/feature_matrix`.

4. **Local scope registration was not idempotent.**  
   Startup and explicit reconcile both validate declared scopes. The registry
   rejects duplicate registration, so `register_scopes()` needed to avoid
   re-registering already-known `(resource_type, resolver)` pairs.

5. **Live token acquisition still hit Keycloak setup state.**  
   Alice's password grant initially returned:

   ```json
   {
     "error": "invalid_grant",
     "error_description": "Account is not fully set up"
   }
   ```

   I cleared Alice's required actions through the Keycloak admin CLI and then
   acquired the token successfully. This is operational friction, not part of
   the feature model.

6. **A full targeted ruff run is noisy because the existing FastAPI style trips
   `B008` throughout `notes.py`.**  
   I verified changed files with `--ignore B008`; the new code had no remaining
   scoped lint issues.

## Required Probe Transcript

### Probe 1: closed area vocabulary

Temporary declaration: `notes.share.project_demo`.

Command:

```text
uv run --project apps/api python -m asunset_core.features.matrix features.yaml --md /tmp/access-matrix-probe.md
```

Failure:

```text
asunset_core.features.manifest.ManifestError: feature 'notes.share.project_demo': segment 'project_demo' not in area 'notes.share' modes ['basic', 'org_wide'] — add the mode to the area or fix the key
```

### Probe 2: unregistered resolver

Temporary declaration: `resolver: approved_only`.

Command:

```text
validate_declared_scopes(load_manifest('features.yaml'))
```

Failure:

```text
asunset_core.features.scopes.ResolverNotRegistered: manifest declares scope resolvers that are not registered: [('note', 'approved_only')]
```

### Probe 3: stale filled skeleton

Temporary declaration change: `notes.share.basic` default grant from
`organization#member` to `organization#admin`.

Command:

```text
uv run --project apps/api pytest tests/feature_matrix/test_matrix_notes_share_basic.py::test_notes_share_basic_declaration_current -q
```

Failure:

```text
AssertionError: declaration of 'notes.share.basic' changed (fingerprint 3043933e01af51e2 != evidenced db838a5f09a92684) — re-verify the matrix-row tests against the new declaration, then update EXPECTED_FINGERPRINT
```

## Live Operation

The rebuilt API started with:

```text
features.reconcile_done declared=5 added=2 orphans=0 pruned=0 disabled=0 dry_run=false
```

That startup hook applied the two new default grants before the manual
reconcile calls. The explicit preview/apply sequence was therefore idempotent:

```json
{
  "added": 0,
  "orphans": [],
  "pruned": 0,
  "disabled": 0
}
```

I assigned Alice to `sharers`:

```json
{
  "assigned": true,
  "noop": false
}
```

Positive explain for Alice:

```json
{
  "allowed": true,
  "steps": [
    {"check": "manifest", "outcome": "ok", "detail": "declared"},
    {"check": "enabled", "outcome": "ok", "detail": "enabled"},
    {"check": "freeze", "outcome": "ok", "detail": "not frozen"},
    {
      "check": "default:role:sharers#assignee",
      "outcome": "grants",
      "detail": "user holds role sharers"
    },
    {
      "check": "authorizer",
      "outcome": "grants",
      "detail": "FGA check(user:d253ea87-1650-49f7-889c-d0cec38a546f, can_use, feature:notes.share.org_wide) = True"
    }
  ]
}
```

Negative explain for plain member
`75cbb12c-7788-49b2-a1f1-2f7b01fa3c9c`:

```json
{
  "allowed": false,
  "steps": [
    {"check": "manifest", "outcome": "ok", "detail": "declared"},
    {"check": "enabled", "outcome": "ok", "detail": "enabled"},
    {"check": "freeze", "outcome": "ok", "detail": "not frozen"},
    {
      "check": "default:role:sharers#assignee",
      "outcome": "not-applicable",
      "detail": "user is not an assignee of role sharers — POST /platform/roles/sharers/assignees would grant it"
    },
    {
      "check": "authorizer",
      "outcome": "not-applicable",
      "detail": "FGA check(user:75cbb12c-7788-49b2-a1f1-2f7b01fa3c9c, can_use, feature:notes.share.org_wide) = False"
    }
  ]
}
```

The new stub endpoint returned `HTTP 200` and `[]` for Alice in the current
data state.

## Runtime Matrix Attachment

```text
# Access matrix — runtime state, generated 2026-07-26T07:24:54.317045+00:00

Design-time baseline: docs/access-matrix.md (generated from the
manifest). Everything under 'Runtime grants' is beyond-design by
definition — provenance answers who granted it and when.

| Capability | State | Default grants | Runtime grants (provenance) |
|---|---|---|---|
| `audit.view` | enabled | organization#member | — |
| `notes.export` | enabled | organization#member | — |
| `notes.archive` | enabled | role:archivists#assignee | — |
| `notes.share.basic` | enabled | organization#member | — |
| `notes.share.org_wide` | enabled | role:sharers#assignee | — |

## Role assignments

- `archivists` ← user:d253ea87-1650-49f7-889c-d0cec38a546f (by d253ea87-1650-49f7-889c-d0cec38a546f at 2026-07-26T03:56:43.026966+00:00)
- `sharers` ← user:d253ea87-1650-49f7-889c-d0cec38a546f (by d253ea87-1650-49f7-889c-d0cec38a546f at 2026-07-26T07:21:34.301313+00:00)
```

## Decision Record Self-Assessment

The decision record is useful because it separates product area, mode
vocabulary, default personas, and resource reach before code changes. It also
states the business-logic contract directly: the feature system does not
replace app authorization. Handlers must compose `require_feature` with
`resolve_scope`, then keep payload/lifecycle/write semantics in the app.

The matrix mental model is correct if treated as a projection of designed
capability rows: capability x default persona x declared resource reach. It is
not the runtime enforcement model and should not become another source of
truth.

## Verification

- `uv run --project apps/api pytest tests/feature_matrix` -> 18 passed.
- `uv run --project apps/api ruff check --ignore B008 ...` -> all checks
  passed for changed Python files.
- `assert_generated_current(...)` -> current.
- Smoke API final rebuild -> healthy.
- `GET /notes/share/org-wide/candidates` -> `HTTP 200`.

## Verdict

PASS with frictions. The capability model works for this shape: the area/mode
vocabulary catches accidental object-instance keys, registered resolvers catch
missing reach implementations, and skeleton fingerprints catch stale evidence.
The main DX fixes I would make before handing this to more sophisticated
consumers are: fix/keep the codegen entrypoint ordering, improve scaffold for
multi-mode areas, document the actual consumer skeleton path, and make live
smoke auth setup independent of Alice's interactive Keycloak required actions.

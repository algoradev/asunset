# Feature-Level Permissions — Design Spec

**Status:** SPEC — approved direction (Avi, 2026-07-23); not yet implemented.
**Depends on:** the identity contract (`docs/identity-contract.md`, rev 3) — in particular D1's human/machine split and the claims-split rule (permissions are never token claims).
**Supersedes:** the realm-role shortcut pattern (e.g. wirebit CRM v1's `crm_support` realm roles) for product feature gating.

---

## 1. Problem

asunset has *resource-level* authorization (this note, this report — owner/editor/viewer with team/org usersets) but **no feature-level dimension**: nothing answers "may this user use `reports.export` at all." Products need it for gating endpoints and rendering menus. The current workaround — product realm roles in Keycloak — bakes authorization into the identity plane, which the contract explicitly forbids: roles in tokens go stale until re-login, revocation waits on token expiry, and every product role change touches the realm.

## 2. Design summary

Features become **OpenFGA objects**; grants become **tuples**; the manifest of what features exist lives **in the consumer repo as a versioned file**, reconciled into tuples on deploy. Tokens do not change. Enforcement is one Authorizer check per gated endpoint; the frontend gets the feature set via `list_objects`.

```
feature manifest (repo, versioned)
        │  reconcile on deploy (add missing, flag orphans)
        ▼
FGA tuples:  feature:reports.export  can_use  organization#member@org:<id>
        │
        ▼                                   ▼
API: require_feature("reports.export")   Web: list_objects(user, can_use, feature)
     → authorizer.check(user:<sub>, …)        → render menus / gate routes
```

## 3. The model — adapted, not transplanted

Two new **optional** platform types in `asunset_core.fga`, composed via the existing `build_model()` path (consumers spread them in exactly like `PLATFORM_TYPES`):

```
type feature
  relations
    define can_use: [user, organization#member, organization#admin,
                     team#member, role#assignee, service_account]

type role
  relations
    define assignee: [user, role#assignee]
```

Deliberate adaptations from the generic "custom roles" pattern:

1. **Grant to the usersets asunset already has.** Org/team roles exist twice today — `org_member.role` in the DB and `organization#admin/member`, `team#admin/member` in FGA — kept coherent by dual-write. A `role:org_admin` object would be a third copy with no owner. So the common grants are direct-to-userset: `feature:X can_use organization#member`. **The `role` type is only for product-defined custom roles beyond admin/member** (e.g. `role:compliance_reviewer`) — genuinely new data, not a mirror. `role#assignee` inside `role` gives inheritance when needed.
2. **Features are instance-global.** One org per instance (D2/D5) means no org-scoping level; the model stays flat. If multi-org ever activates via `X-Org-Id`, feature scoping is revisited then — not speculatively now.
3. **`service_account` is for machines only** (CI, external integrations), receiving direct feature tuples. Per D1, agents are *never* service accounts — an agent inherits its human's features like everything else. This grantee type ships with the model so machine callers don't force a redesign, but the agent path never uses it.
4. **Time-boxed grants** use FGA conditional tuples (`valid_until` checked at evaluation) — the same mechanism D4 adopts for session scope-down. Revocation is tuple deletion: instant, no token gymnastics.

## 4. The manifest

One file in the consumer repo (`features.yaml`), the single source of truth for what features exist:

```yaml
# features.yaml — reconciled into FGA tuples on deploy
features:
  reports.export:
    description: "Export reports to CSV/PDF"
    grants:
      - organization#member
  billing.manage:
    description: "Manage billing settings"
    grants:
      - organization#admin
  compliance.review:
    description: "Review flagged items"
    grants:
      - role:compliance_reviewer#assignee
```

Rules:

- **Key format:** `domain.verb`, lowercase, dot-separated. The key *is* the FGA object id (`feature:reports.export`).
- `grants` entries are either a platform userset (`organization#member`, `team#member`) or a role userset (`role:<name>#assignee`). Direct user grants are runtime data (admin UI / API), **never** manifest entries — the manifest declares defaults, not people.
- Codegen emits constants for both sides (Python enum + TS union) from the same file, so `feature:reports.exprot` is a compile-time error, not a silent 403.

## 5. Reconciliation

Extends the existing `reconcile.py` pattern (`fga.drift_detected`/`fixed` events):

- **On deploy** (or `python -m <product>.reconcile --features`): for each manifest feature, write missing `can_use` tuples with `tolerate_existing=True`; create missing `role:` objects implied by grants.
- **Orphans** (tuples for features no longer in the manifest): **flag, never auto-delete** — emit `fga.feature_orphan` audit events and require an explicit `--prune` to remove. Same fail-toward-orphan-tuples posture as the dual-write discipline.
- Runtime user-level grants (`user:<sub> can_use feature:X`) are untouched by reconcile — it owns only manifest-declared userset grants.

## 6. Enforcement

**Backend** — one new dependency in the platform chain:

```python
def require_feature(key: str):
    async def _dep(
        principal: Principal = Depends(get_current_principal),
        authz: Authorizer = Depends(get_authorizer),
        sink: AuditSink = Depends(get_audit_sink),
    ) -> None:
        allowed = await authz.check(principal.fga_user(), "can_use", f"feature:{key}")
        if not allowed:
            await sink.emit(EventType.access_denied, action="feature_check",
                            resource_type="feature", resource_id=key,
                            permission="can_use", success=False)
            raise HTTPException(403, f"feature {key} not enabled for user")
    return _dep

@router.post("/reports/export", dependencies=[Depends(require_feature("reports.export"))])
```

Denials are audited with the standard actor snapshot — feature denials become SIEM-visible like every other authz event.

**Frontend** — `GET /me/features` (new platform endpoint) returns `list_objects(user:<sub>, can_use, feature)`; the web shell exposes it as a `useFeatures()` hook for menu/route gating. UI gating is UX only — the API check is the control.

## 7. CI

- Model assertions in `.fga.yaml` (`fga model test`): per-persona checks (org member can use X, cannot use Y; role assignee inherits; conditional tuple expires). Runs in CI next to the model file.
- Manifest lint: keys well-formed, grants reference known usersets/roles, codegen output up to date.
- These slot into the security-path test commission as the FGA phase's feature cases.

## 8. Non-goals

- **No token changes.** Features are never claims. (Contract §0/§9.)
- **No `role` mirror of org/team admin/member.** (§3.1 above.)
- **No org-scoped features** while one-org-per-instance holds.
- **No agent-as-service-account.** (D1.)
- **No admin UI for features in v1** — manifest + reconcile + (existing) FGA tuple writes cover it; a management surface is a later product decision.

## 9. Implementation order

1. `asunset_core.fga`: add `FEATURE_TYPE` / `ROLE_TYPE` (+ DSL mirror in docs), export alongside `PLATFORM_TYPES`.
2. Manifest schema + loader + codegen (`asunset_core.features`).
3. Reconcile extension (`--features`, orphan flagging).
4. `require_feature` dep + `GET /me/features` + `useFeatures()` hook.
5. `.fga.yaml` test harness in CI.
6. Wire one real feature through the Notes demo end-to-end as the reference; update `consuming-template` with a worked example.

# Feature-Level Permissions — Design Spec

**Status:** IMPLEMENTED v1 (25e24d3) + feat-ops 1–3 (gate validation, reconcile endpoint, enabled:false kill switch). §10 (runtime-grants surface) is the planned v1.1.
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

---

## 10. Feature operations (v1.1) — runtime-grants surface [REVIEW-CONSOLIDATED, ready to build]

Reviewed adversarially by kestrel (ops), relay (consumer/portability), and juniper (generalization) — thread b999a0d238e5, 2026-07-25. Unanimous: cycle-A (manifest-default) features are production-shaped today; anything runtime-granular waits for v1.1. **Hard rule (juniper, effective immediately): no hand-tuple-writing as interim practice — if the surface doesn't exist, the feature waits.**

### Already shipped from the reviews (small fixes, same day)

- **Runtime-only features** (relay's hard issue): `grants: []` is legal — declared, gate-validated, zero defaults; every grant is runtime data. No more overexposure/dummy-role workarounds.
- **`dry_run` on reconcile** (kestrel): full would-do report, zero writes, no audit event — the read-only drift assessment consumer doctors consume instead of reimplementing the diff. Doctor VERIFIES; only the audited endpoint MUTATES (ruled: no doctor `--fix`, ever).
- **Reconcile-time gate validation** was already present (reconcile refuses removing a manifest key a gate still declares — kestrel's delayed-landmine catch); boot-failure severity ratified via the internal-consistency-vs-external-availability rule: fail-closed at boot only for same-artifact config bugs, degrade+alarm for dependency blips.

### v1.1 endpoints (org-admin gated unless noted; every mutation audited)

| Verb | Path | Effect |
|---|---|---|
| GET | `/platform/features` | Manifest view + per-feature grant listing **with provenance** (juniper #1): origin manifest-default vs runtime, granted_by, granted_at, creating audit event id |
| POST | `/platform/features/{key}/freeze` · `/unfreeze` | **Incident freeze** (kestrel's headline): deny-all-now, PRESERVES every grant tuple, reversible in one call, runtime-only (no manifest edit), audited. Distinct axis from `enabled: false` = decommission (destructive, deliberate, deploy-time — unchanged). **Ships in lockstep with its runbook invocation** (documented command, token custody pre-solved) — endpoint + invocation are one deliverable |
| POST | `/platform/roles/{role}/assignees` | assign human to custom role (`role.assigned`) |
| DELETE | `/platform/roles/{role}/assignees/{user_id}` | revoke — **idempotent audited no-op if absent, never 404** (juniper #3: re-runnable runbooks) |
| GET | `/platform/roles` · `/platform/roles/{role}/assignees` | roles + membership listing (juniper #4: "who holds billing_ops" must not require reading tuples) |
| POST / DELETE | `/platform/features/{key}/grants` | per-user / per-team runtime grants (`feature.granted` / `feature.revoked`), same idempotent-revoke rule |

Rules carried forward: `{key}` must exist in the manifest (no shadow features); disabled AND frozen features refuse new grants; dual-write ordering; audit payloads carry grantee + grantor snapshots. New `EventType` members: `ROLE_ASSIGNED`, `ROLE_UNASSIGNED`, `FEATURE_GRANTED`, `FEATURE_REVOKED`, `FEATURE_FROZEN`, `FEATURE_UNFROZEN`.

### Also in v1.1 (review commitments)

- **Close the orphan hole** (juniper #2): a full-sweep reconcile mode that enumerates `feature:*` grants via the runtime-grant bookkeeping (freeze/grant state gives us the object index the FGA Read API can't) and flags any key absent from the manifest — the role-grant-on-removed-feature leak stops being a documented limitation.
- **Tombstone lifecycle rule** (relay #4, doctrine now, enforced then): feature retirement is a transition, not a disappearance — `enabled: false` → reconcile/sweep → remove the key only when provably grant-free. v1.1's reconcile refuses removing a key that still has discoverable grants.
- **Codegen in CI** (relay #5): consumers wire the enum/union generation and a generated-files-current check; consuming-template gets the recipe.
- **`dry_run` doctor reachability** (kestrel DX review): `dry_run` is a read and must be callable by the consumer doctor's instance/service identity — a machine-credential auth path (design item: KC service-account token with a proper audience, or an operator API key) rather than inheriting the mutating endpoint's `platform_admin` bar. Report output deterministically ordered so drift is diffable.
- **Point-in-time access-matrix export** (kestrel DX review): the live feature → grant → who matrix with provenance, dated, exportable — the compliance-audit artifact. Rides the provenance listing.

### Doctrine lines for consuming-template docs (juniper, written rules not oral tradition)

1. **Features gate SURFACES; governed-writer/gate invariants govern ARTIFACTS.** They compose; neither substitutes for the other. A feature grant never bypasses an artifact invariant; artifact approval never implies a feature.
2. **Feature keys are object-free** — `domain.verb`, never `domain.verb.<object-instance>`. Per-object questions belong to resource relations (compose `require_feature` + per-object check). *Note an open convention tension: juniper wants ≥3-segment keys rejected structurally; relay wants owned prefixes (`opsroom.tables.create` — 3 segments) for cross-product namespacing. Resolution proposal: multi-segment stays legal (namespacing is legitimate), the ban is on object-INSTANCE segments — doctrine + review, with the no-shadow-features rule as the structural backstop. Flagged for a joint ruling if either side objects.*
3. **This is a permission system, not a flag service** — no percentage rollouts, no per-request config; if flag semantics are ever needed, shop for a flag tool.

Out of scope for v1.1 (unchanged): admin UI (API-first), conditional-tuple trials (D4 end-state).

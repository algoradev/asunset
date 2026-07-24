# asunset Identity Contract

**Status:** RATIFIED (rev 3). D1–D6 decided by Avi, 2026-07-23. Consumers may build against this contract.
**Scope:** asunset is the auth and permissions system **for the whole platform**, not an IdP for any one consumer. This document describes the identity contract every consumer rides.
**Verified against:** `main` / `fb4e995`. Every claim is anchored to a file so it can be re-verified rather than trusted.

§1–§10 are descriptive (what the code does today). §11 records the ratified decisions; where a ruling implies work not yet built (D4, D5, D6), the section says so explicitly — a ruling is a direction, not a shipped feature.

### Consumers this contract serves

| Consumer | What it needs from identity |
|---|---|
| **Product API gate** | Per-request principal for every human *and* agent data operation. |
| **Web UI** | Login, session lifetime, idle logoff, logout — the whole authenticated chrome. |
| **Orchestration + MCP** | Token validation as a pure resource server; session semantics for agent-executed work. |
| **Audit / lifecycle rails** | Actor attribution on every event, for humans, agents, and service flows alike. |

> **Revision note.** Rev 1 was written through the opencode/MCP lens. Rev 2 broadened to platform scope; the three ratification-stable facts — the claims split (§7), `sub`-as-key (§4), split-issuer validation (§5) — survived unchanged. Rev 3 records the ratified decisions in §11 and supersedes rev 2's open-questions framing.

---

## 0. The one-paragraph version

asunset is a Keycloak-fronted identity plane. A browser SPA (`asunset-web`, public client, authorization code + PKCE S256) obtains an RS256 JWT. Any resource server validates that JWT **offline** against JWKS and derives a **`Principal`** — *person identity plus instance-level realm roles, and nothing else*. **Organization, team, and per-resource authority are deliberately NOT in the token**; they are resolved per-request from the database and from OpenFGA. A service that treats the token as the whole authorization story will be wrong. That split is the contract, and it holds identically for the UI, the product API, MCP, and the audit rails.

---

## 1. The identity plane

```
Browser ──auth code + PKCE──> Keycloak (realm: asunset)
                                 │  mints RS256 JWT, aud = asunset-api
                                 ▼
        ┌────────────────────────────────────────────────┐
        │  Any resource server (product API, MCP, …)     │
        │  1. validate offline vs JWKS      → claims     │
        │  2. build Principal               → person+roles│
        │  3. resolve org from DB           → OrgContext │
        │  4. open RLS-scoped session       → tenant fence│
        │  5. ask Authorizer per object     → decision   │
        │  6. emit audit w/ actor snapshot  → attribution│
        └────────────────────────────────────────────────┘
```

Steps 3–6 are *not* in the token. They are the contract's substance as much as step 1 is.

---

## 2. The token

### 2.1 Clients

Two clients exist in the realm (`infra/keycloak/realm-export.json`):

| Client | Type | Flow | Purpose |
|---|---|---|---|
| `asunset-web` | **public** | authorization code, **PKCE `S256` enforced server-side**; implicit off; direct access grants off | The only client that mints end-user tokens. |
| `asunset-api` | **confidential** | standard flow **off**; service account **on** | Not a login path. Its service account holds `manage-users` for the invite flow. Its client-id is the **audience** every user token is checked against (§3). |

PKCE is not merely a client-library choice — `pkce.code.challenge.method: S256` is set as a client attribute, so Keycloak rejects a code exchange without a valid verifier regardless of what the frontend does.

### 2.2 Claims present and consumed

Mappers on `asunset-web`: `realm-roles` (multivalued → `realm_access.roles`) and `audience-api` (adds `asunset-api` to `aud`, **access token only**).

Claims read by `packages/asunset_core/src/asunset_core/auth/oidc.py`:

| Claim | Required | Used for |
|---|---|---|
| `sub` | **enforced** | UUID → `Principal.user_id`, **and** the primary key of the local `app_user` mirror, **and** the OpenFGA subject `user:<sub>`. The identity join key for the entire platform. |
| `iss` | **enforced** | Must equal the **public** issuer exactly (§5.1). |
| `aud` | **enforced** | Must contain the configured API client id (§3). |
| `exp`, `iat` | **enforced** | Expiry. |
| `realm_access.roles` | no | → `Principal.realm_roles`. |
| `email` | no | → `Principal.email`; falls back to `{preferred_username}@unknown`. |
| `name` / `given_name`+`family_name` / `preferred_username` | no | → `Principal.display_name`, in that precedence order. |
| `sid` | no | → `Principal.session_id`; carried into audit for credential-misuse detection. |

`options={"require": ["exp","iat","sub","iss","aud"]}` — a token missing any of these is **rejected**, not defaulted.

### 2.3 Realm roles

Exactly two, both **instance-level**, neither org-scoped:

- **`platform_admin`** — operates the instance (orgs/teams, Keycloak config, OpenFGA store).
- **`platform_support`** — read-only observability; may carry impersonation rights per operator policy.

There is no `org_admin` realm role. Org role is a database fact (§7.1).

### 2.4 Lifetimes and session policy

| Setting | Value | Where set | Re-pushed on restart? |
|---|---|---|---|
| Access token lifespan | **900 s** | client attribute `access.token.lifespan` on *both* clients, plus realm `accessTokenLifespan` | **No** |
| `ssoSessionIdleTimeout` | **900 s** | `infra/keycloak/init.sh` | **Yes, every start** |
| `ssoSessionMaxLifespan` | **14400 s (4 h)** | `init.sh` | **Yes, every start** |
| OTP policy | `totp`, HmacSHA1, 6 digits, 30 s, look-ahead 1 | `init.sh` | **Yes, every start** |
| `bruteForceProtected` | true | realm import | No |
| `registrationAllowed` | false | realm import | No |
| `sslRequired` | `external` at import → forced **`all`** on any https deployment | `init.sh` | Yes, when https |

Two operational consequences worth knowing platform-wide:

1. **`--import-realm` uses IGNORE_EXISTING on reboot.** Edits to `realm-export.json` do *not* propagate after first import — which is why session/OTP knobs are re-pushed via `kcadm` every start. **Access-token lifespan is not in that re-push set**, so on a long-lived instance it is whatever the first import set and will not self-heal if changed by hand.
2. **TOTP is force-enrolled on every `platform_admin` holder** at each init, skipping already-enrolled users — HIPAA §164.312(a)(2)(i) / NYDFS 500.12.

---

## 3. Audience strategy

### 3.1 What is true today

**There is exactly one audience on the platform, and every resource server shares it.**

- The audience mapper on `asunset-web` injects a single value: the `asunset-api` client id.
- Validation checks `audience=settings.keycloak_api_client_id` (`config.py`).
- **A consumer product's API reuses the same value.** `consuming-template/compose.product.yml` passes `KEYCLOAK_API_CLIENT_ID` straight through to the product API, and the product app is otherwise a copy of `asunset_api`'s `main.py`. So the demo API, a consumer product API, and any future resource server all validate against the *same* audience.

This is a real property, but note *how* it arises: it is the consequence of every service reusing one config field, not the outcome of a considered multi-resource-server design. It answered the single-resource-server case correctly and was never stress-tested beyond it.

### 3.2 What the platform scope reopens

With a product API gate, MCP, and orchestration as **distinct resource servers**, "one shared audience" now means any token minted for the UI is equally valid at every one of them. There is no cryptographic distinction between a token intended for the product API and one presented to MCP.

The options — genuinely a decision, not a description, and routed as **D6**:

| Option | Effect |
|---|---|
| **One platform audience** (status quo) | Simplest. Any valid token is accepted everywhere; separation rests entirely on the Authorizer, not the credential. |
| **Per-resource-server audiences** | Each RS validates its own `aud`. A token minted for the UI is *not* automatically valid at MCP. Requires a client (or audience mapper) per RS and interacts with **D3** (realm shape). |
| **`aud` array** | One token, multiple accepted audiences; RSes still check for their own. Middle ground; keeps one login, restores per-RS distinction. |

This interacts directly with **D4** (scope-down): per-RS audiences are the cheapest form of "this credential is not valid everywhere," and may satisfy part of what agent sessions need without building scope machinery.

---

## 4. The `Principal` object

`packages/asunset_core/src/asunset_core/auth/principal.py` — frozen, slotted:

```python
@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID                 # == token `sub` == app_user.id == FGA user:<sub>
    email: str
    display_name: str
    realm_roles: frozenset[str]   # realm roles ONLY
    session_id: str | None        # Keycloak `sid`

    @property
    def is_platform_admin(self) -> bool: ...
    @property
    def is_platform_support(self) -> bool: ...
    def fga_user(self) -> str: ...   # -> f"user:{user_id}"
```

Its docstring states the load-bearing rule:

> Roles here are realm roles only (platform_admin, platform_support) — per-org / per-team / per-resource authorization is answered by the Authorizer port, never by inspecting this object.

`fga_user()` is the bridge to authorization: the OpenFGA subject is literally `user:<sub>`.

**Mirror side-effect.** `get_current_principal` upserts `app_user` on *every* authenticated request, so email/display-name changes in Keycloak propagate on next call. `app_user` is deliberately excluded from RLS tenant tables — it is a global dimension, and the upsert must work for a user who has no org yet. **Consequence for every consumer: `sub` is durable, `email` is not.** Persist `sub`.

---

## 5. How a resource server validates a token

The algorithm in `oidc.py:_validate_token`. Any resource server — product API, MCP, orchestration — should implement exactly this.

1. **Bearer only.** Missing/non-bearer → `401 missing bearer token`.
2. **Read `kid`** from the unverified header. Missing → `401 token missing kid`.
3. **Fetch JWKS** from `{internal_issuer}/protocol/openid-connect/certs`, cached **300 s**.
4. **Rotation tolerance:** `kid` absent from the cached keyset → invalidate and re-fetch **once**; still absent → `401 signing key not found in JWKS`.
5. **Decode** with `algorithms=["RS256"]`, `audience=<api client id>`, `issuer=<public issuer>`, requiring `exp/iat/sub/iss/aud`.

### 5.1 The split-issuer rule — the detail that breaks integrations

> JWKS is fetched from the **internal** issuer. The `iss` claim is validated against the **public** issuer.

Two distinct settings (`config.py`): `keycloak_issuer` (browser-facing; what `iss` must equal) and `keycloak_internal_issuer` (in-network service DNS; signing keys only). The module docstring calls this "the single most common cause of 'works on localhost, breaks in compose' bugs," and the mismatch error names the fix. In tailnet/TLS mode Keycloak runs under an `/auth` path prefix, so **both** issuers carry it: internal `http://keycloak:8080/auth`, public `https://<host>/auth/realms/<realm>`.

### 5.1a Two issuers (amendment, D7 = A — 2026-07-24)

With the D4 mint shipped, the platform has **two token issuers**, selected by the `iss` claim:

| `iss` | Token | JWKS source |
|---|---|---|
| the Keycloak public issuer (§5.1) | login tokens | Keycloak JWKS (internal issuer URL) |
| `urn:asunset:sessions:<realm>` (or `SESSION_TOKEN_ISSUER`) | agent session tokens (`typ: asunset-session`) | `GET /platform/sessions/jwks` on the platform API (in-network) |

A validator reads the **unverified** `iss` only to select which path to run; the selected path then verifies everything — including `iss` — cryptographically. All other rules are identical across both paths: RS256 only, the five required claims, and per-RS `aud` validation (session tokens carry an `aud` *subset*, so a resource server absent from the subset rejects the token exactly as in §3/D6). Session tokens additionally require `sid`, `typ = asunset-session`, and an `act.sub` of the form `agent:<agent_id>`; their `sub` is **always the human** (D1), and asunset builds their `Principal` with an **empty realm-role set** — agent sessions never wield `platform_admin`/`platform_support`.

The token alone is never sufficient for a session: the `agent_session` row (revocation/expiry state, grant subset) is re-read on every request, and effective permission is *grant subset ∩ the human's live permissions* (see `docs/session-token-mint-spec.md`).

### 5.2 Failure modes are distinguishable

All `401`, distinct messages: `malformed token`, `token missing kid`, `signing key not found in JWKS`, `token expired`, `wrong audience`, `issuer mismatch — check KEYCLOAK_PUBLIC_URL matches what the browser uses`.

### 5.3 Configuration needed

`keycloak_issuer` (public), `keycloak_internal_issuer` (JWKS-reachable), expected audience. Validation is **fully offline** after JWKS retrieval — no introspection endpoint, no shared secret, no call back into asunset on the request path.

---

## 6. Human sessions — the web UI flow

The surface asunset owns and every product UI rides. Two layers: what Keycloak enforces, and what the SPA does.

### 6.1 The login flow

`apps/web/src/auth.ts` — `react-oidc-context` over `oidc-client-ts`:

| Setting | Value |
|---|---|
| `authority` | `${VITE_KEYCLOAK_URL}/realms/${VITE_KEYCLOAK_REALM}` |
| `response_type` | `code` (authorization code; PKCE S256 enforced by the client config, §2.1) |
| `scope` | `openid profile email` |
| `redirect_uri` / `post_logout_redirect_uri` | `window.location.origin` |
| token storage | **`localStorage`** |
| `automaticSilentRenew` | **true** |
| `onSigninCallback` | strips `?code=…&state=…` from the URL after callback |

Redirect URIs, web origins, and post-logout URIs are **derived from the deployment hostname** by `init.sh`, not hand-set per environment. On a tailnet deployment the script fails loud rather than leaving localhost URIs in place.

**Storage caveat, stated in the source:** `localStorage` is a deliberate template trade-off ("acceptable for a solo-operator dev template; tighten to `sessionStorage` or memory in deployments where XSS is a concern"). Refresh tokens live there too. **Any product handling regulated data should revisit this** — it is a template default, not a HIPAA-considered ruling.

### 6.2 Idle logoff

`apps/web/src/lib/useIdleLogout.ts` — HIPAA §164.312(a)(2)(iii) "Automatic logoff".

- Tracks `mousemove`, `mousedown`, `keydown`, `touchstart`, `scroll`, `wheel`.
- **15 minutes idle → sign-out**, with a **1-minute warning** countdown dialog.
- Deliberate subtlety: activity does **not** reset the clock once the warning is showing — otherwise mouse movement over the dialog itself would silently cancel the logout.
- Aligned by design with `ssoSessionIdleTimeout` (900 s).

**The authority relationship matters:** the hook's own docstring is explicit that **Keycloak's server-side idle timeout is the authoritative cap**; the hook is the UX layer that makes logoff visible before the next request 401s. A consumer UI may restyle or re-time the dialog, but must not treat the client-side timer as the security control.

### 6.3 Session identifiers

`sid` flows from the token into `Principal.session_id` and onward into every audit row (§8), so one SSO session correlates across the UI, the API, and the SIEM feed.

---

## 7. What is *not* in the token: org, team, resource authority

The section most likely to surprise an integrator — and it applies to every consumer class equally.

### 7.1 Org is resolved from the database, per request

`apps/api/src/asunset_api/routers/deps.py` — `get_current_org` queries `org_member`. There is no org claim.

- The RLS session is opened with only `app.current_user_id` set; `org_member`'s policy permits self-rows, which makes this bootstrap-safe.
- **One-org-per-instance is an explicit assumption**: multiple memberships → takes `memberships[0]`, with a comment noting a multi-client instance would need an `X-Org-Id` header (**D5**).
- No membership + `platform_admin` → `409 no org provisioned yet — call POST /platform/bootstrap`. Otherwise → `403 user has no org membership`.

`OrgContext` carries `org_id` and a DB-sourced `role`, exposing `is_admin`. **Org admin-ness is a database fact, not a token claim.**

### 7.2 Team membership lives in the database and OpenFGA only

`Principal` has no team field and no team claim is minted. Team-derived access is answered by OpenFGA, where `team#member` is a grantee type.

### 7.3 Tenant scoping is transaction-local Postgres settings

`get_db` sets `app.current_user_id` and `app.current_org_id` via `set_config(..., true)` — the trailing `true` makes them **transaction-local**, so they cannot leak across pooled connections. RLS policies on the six tenant tables key off `app.current_org_id`. OpenFGA stays authoritative for authorization; RLS is defense-in-depth.

### 7.4 The composed dependency chain *is* the security property

```
get_current_principal → get_current_org → get_db (RLS-scoped) → get_authorizer → get_audit_sink
```

`deps.py` says it outright: routers depend on the composed helpers, not on reaching through the chain manually — "the layering is the security property, not a convention." A consumer product mounts asunset's platform routers and adds its own, inheriting this chain rather than reimplementing it.

---

## 8. Audit and lifecycle rails — actor attribution

`packages/asunset_core/src/asunset_core/audit/sink.py`. Identity's obligation to the audit feed, for humans, agents, and service flows alike.

**Identity is snapshotted once per request**, at `AuditSink` construction — explicitly "so the resulting rows are immune to user deletion / role changes that happen after the fact." An audit row records who the actor *was at the time*, not who they are now.

Every event carries:

| Field | Source |
|---|---|
| `actor_id` | `Principal.user_id` (= `sub`) |
| `actor_email`, `actor_display_name` | `Principal` (mirror snapshot) |
| `actor_org_role` | `OrgContext.role` — the DB fact, not a claim |
| `actor_realm_roles` | `Principal.realm_roles`, sorted |
| `session_id` | token `sid` |
| `org_id` | `OrgContext.org_id` |
| `trace_id` | `CorrelationIdMiddleware` (request-ID correlation) |
| `source_ip` | `X-Forwarded-For` left-most when present, else peer |
| `user_agent` | truncated to 500 chars |
| `permission`, `permission_path` | the Authorizer's decision *and how it resolved* (direct / team / org) |

Each `emit()` **dual-writes**: an enriched row into `audit_event` (in-app viewer, short retention) and the same structured record to stdout for Vector → SIEM (long-retention source of truth). Payload and resource label pass through the **Redactor port** first.

Two notes for consumers:

- `EventTypeLike` accepts any str-enum with `.value`, so a product defines its own event types without extending the platform enum — and a bare `str` is rejected by type-checkers before it reaches runtime.
- **`source_ip` is only as trustworthy as the proxy.** `deps.py` states the requirement: operators running behind a reverse proxy **must** configure it to set `X-Forwarded-For` and strip client-supplied values. Without that discipline the header is spoofable.

**Open, not resolved here:** the Redactor is a port with a **no-op default**. What counts as PHI is a policy decision upstream of any implementation (tracked separately as A2).

---

## 9. Per-session scope-down

> **Update 2026-07-24:** the D4 mint now exists — `POST /platform/sessions` issues scoped agent session tokens per `docs/session-token-mint-spec.md`, validated per §5.1a. The analysis below described the pre-mint state and remains accurate for **login tokens**, which still carry the user's full authority.

**Login tokens have no scope-down.** Verified negatives at `fb4e995`:

- **No OAuth scopes in play.** `clientScopes` is `[]`; neither client declares `defaultClientScopes`; nothing in the auth path reads a `scope` claim. (The SPA requests `openid profile email` — standard OIDC identity scopes, which carry no authorization meaning here.)
- **No token exchange.** `TOKEN_EXCHANGE` appears in the realm export only as an enabled *audit event type*, not as an enabled Keycloak feature — it is a preview feature requiring explicit activation, and nothing activates it.
- **No delegated or down-scoped grants.** The only `client_credentials` use is `asunset-api`'s service account for Keycloak admin calls during invites — an instance-level machine credential, unrelated to narrowing a user session.

**What narrows authority today is the decision point, not the credential.** Every token carries the user's full capability set; the Authorizer answers "may `user:<sub>` do X to object Y" one object at a time.

**Therefore:** any consumer needing a credential that is *strictly less capable* than the user's full authority — agent-executed sessions being the clearest case, but equally a delegated support session — requires a **new capability to be designed**, not an existing one to be described. Routed as **D4**, and see **D6**: per-resource-server audiences are the cheapest partial answer and may cover some of this need without new machinery.

---

## 10. Integration guidance by consumer class

**Universal — every consumer:**
1. Validate exactly per §5. Offline, RS256, audience, public-issuer `iss`, require the five claims, rotation-tolerant JWKS caching.
2. **Key off `sub`.** Never persist identity by email (§4).
3. Treat `realm_access.roles` as **instance-operator roles only**. Correct for "may this caller administer the deployment"; wrong for anything tenant- or resource-scoped.
4. Never build authorization from role-string inspection — that reimplements the Authorizer, incorrectly.
5. Do not assume a token is scoped to a subset of the user's authority (§9), nor that it was minted for *your* service specifically (§3).

**Product API gate:** mount asunset's platform routers and inherit the composed dependency chain (§7.4) rather than assembling principal/org/session yourself. Emit audit through the sink so attribution matches the rest of the platform (§8). Define product event types as a str-enum.

**Web UI:** ride the flow in §6. Keycloak's `ssoSessionIdleTimeout` is the authoritative session cap; the idle hook is UX. Redirect/origin URIs are derived from the deployment hostname — do not hand-set them per environment. Revisit `localStorage` token storage for regulated deployments.

**Orchestration + MCP:** pure resource server — validate and stop. No login UI, no introspection call. Carry `sid` into your own records so sessions correlate. §9 is the constraint to design around, and §3/D6 determines whether a token minted for the UI is meant to be valid at your endpoint at all.

**Audit / lifecycle rails:** actor attribution is snapshot-at-request, immune to later mutation (§8). Correlate on `trace_id` across feeds and on `session_id` across a session. Treat `source_ip` as trustworthy only under the documented proxy discipline.

---

## 11. Ratified decisions (Avi, 2026-07-23)

### D1 — A user is a human. Agents inherit human permissions; agent sessions must be attributable.

The identity model has one class of person: humans, as Keycloak realm users. Agents do **not** get their own realm identities or service accounts — an agent acts *as* its human, inheriting the human's permissions, and `sub` stays the human's UUID so audit attribution to a person is never severed.

The additional requirement: **which agent session performed an action must be recoverable from audit.** Direction: each agent session gets its own minted token (`sub` = the human, plus agent identity and a fresh session id) so the existing `sid` → `Principal.session_id` → audit-row plumbing (§8) distinguishes agent sessions with no audit-schema change. Until that mint exists (see D4), trusted orchestration may convey `agent_id` as asserted per-request metadata landed on the audit snapshot — acceptable only from trusted infrastructure, since it is not cryptographic.

**Corollary:** the "service account with direct FGA tuples" pattern is reserved for genuine machine callers (CI, external integrations). Modeling an agent as a service account would sever exactly the attribution this ruling requires — do not do it.

### D2 — The asunset `organization` row is the org; consumer config points at it.

One org per instance (settled; see D5). The row created by `POST /platform/bootstrap` is the single source of truth. A consumer's config (e.g. OpsRoom's `context.yaml`) stores a **reference** — the org UUID — never a parallel definition. At boot (or in a `doctor` check) the consumer asserts its configured org id matches the single row in asunset's DB and **fails loud on mismatch**. No linkage table, no sync job.

### D3 — Closed, not applicable.

Two asunset-based products sharing one production server is **not a supported or intended deployment**. One product per production server; each deployment ships its own full stack (own Keycloak, own realm, own users). No shared-identity design exists or is planned. (Co-hosting asunset alongside one product's *own services* on a box — the co-boot spike — is unaffected; that is one product.)

### D4 — Scope-down will be built: asunset-minted session tokens, intersection at the Authorizer.

Ratified direction (full spec is a follow-up artifact, not this document):

- A platform endpoint mints **short-lived session tokens**: human token in → JWT out with `sub` = the human, agent identity claims, a fresh session id, and a declared capability subset.
- **Semantics: effective permission = session's declared subset ∩ the human's live permissions**, enforced at the Authorizer decision point — never encoded as a self-sufficient credential. A scoped token can never outlive a revocation: remove the human's access and every derived session dies with it.
- Time-boxing and instant revocation ride **OpenFGA conditional tuples** (e.g. `valid_until` evaluated at check time) on a session object; revocation = tuple delete, no blocklists, no waiting for token expiry.
- This mechanism is also how D1's per-agent-session attribution is delivered.

### D5 — One org per instance stands; `X-Org-Id` is adopted as future-proofing.

The one-org assumption remains the deployment model. `get_current_org` will accept an **optional `X-Org-Id` header**: when present, validate the caller's membership in that org (403 otherwise); when absent, current behavior. Ships inert on every one-org instance; multi-org later becomes "send the header," not a migration.

### D6 — Audience strategy: `aud` array.

Single login client stays. Tokens carry an **array of audiences** — one entry per resource server the session may touch (e.g. `["asunset-api", "opsroom-mcp", "orchestration"]`), added via audience mapper values. **Each resource server validates its own entry.** A token minted without a given RS's audience is rejected there cryptographically, restoring per-service distinction without per-RS clients or realm-shape churn. Interim/agent session tokens (D4) may be minted with a **subset** of the array — the free half of scope-down. Per-RS confidential clients are introduced only if a service someday needs its own outbound credential, not for validation.

---

## Appendix — verification pointers

| Concern | File |
|---|---|
| Token validation, JWKS, claim extraction | `packages/asunset_core/src/asunset_core/auth/oidc.py` |
| `Principal` shape; roles-vs-authz rule | `packages/asunset_core/src/asunset_core/auth/principal.py` |
| Issuer split, audience, settings | `packages/asunset_core/src/asunset_core/config.py` |
| Org resolution, RLS scoping, dep chain, proxy discipline | `apps/api/src/asunset_api/routers/deps.py` |
| Realm, clients, mappers, PKCE, lifetimes | `infra/keycloak/realm-export.json` |
| Session/OTP policy, URI derivation, TOTP enforcement | `infra/keycloak/init.sh` |
| Authorizer port (the decision point) | `packages/asunset_core/src/asunset_core/auth/authorizer.py` |
| Audit actor snapshot, dual-write, redaction | `packages/asunset_core/src/asunset_core/audit/sink.py` |
| Web login flow | `apps/web/src/auth.ts` |
| Idle logoff | `apps/web/src/lib/useIdleLogout.ts` |
| Consumer API reusing the platform audience | `consuming-template/compose.product.yml` |
| Tailnet issuer/path-prefix wiring | `compose.tailscale.yml` |

**Assurance status (updated 2026-07-24).** The security-path commission is complete — the load-bearing claims in this document are now **test-verified**, not merely code-verified:

- **§5 token validation** — 13 tests against a real ephemeral Keycloak importing the production realm export (`test_jwt_validation.py`): required claims, both audience-rejection branches, real expiry, split-issuer mismatch, alg-none downgrade, forged signatures, key-rotation tolerance, JWKS caching.
- **§7.3 RLS fence** — 14 adversarial tests as the app role running raw SQL against a real Postgres provisioned by the production init script (`test_rls_isolation.py`).
- **§7 Authorizer decisions** — 15 tests against a real ephemeral OpenFGA with the production model (`test_fga_semantics.py`), including the audit `permission_path` vocabulary and the dual-write retry contract.
- **§5.1a session tokens** — 19 hermetic tests (`test_session_tokens.py`).

Still outstanding: a live-composed-stack smoke (login → mint → API through Caddy) that verifies deployment *wiring* rather than logic, tracked in the commission thread.

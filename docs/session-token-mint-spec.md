# Agent Session Tokens — D4 Mint Design Spec

**Status:** SPEC — implements the ratified D4 direction (identity contract §11); target per Avi 2026-07-24: agents cryptographic at adoption day, with the pre-agreed fallback that adoption never waits on this (interim = orchestration-asserted `agent_id`).
**Contains one open decision:** **D7 — signing authority** (§3), surfaced early per kestrel because it touches every resource server. Recommendation included; Avi rules.

---

## 1. What is being built

A platform endpoint that turns a human's session into a **scoped, attributable agent session**:

```
POST /platform/sessions           (auth: the human's normal bearer token)
{
  "agent_id":  "vanta",                     # stable agent identity, caller-declared
  "audiences": ["opsroom-api"],             # SUBSET of the deployment's aud array
  "ttl_seconds": 1800,                      # capped by SESSION_TOKEN_MAX_TTL (default 3600)
  "grants": [                               # capability subset, FGA tuple shapes
    {"relation": "can_view", "object": "report:*"}   # v1: object patterns per product model
  ],
  "label": "nightly digest run"             # audit-facing description
}
→ 201
{
  "session_id": "<uuid>",
  "token": "<RS256 JWT>",
  "expires_at": "..."
}
```

Token claims (the asunset-shaped promise from the contract, kept):

| Claim | Value |
|---|---|
| `sub` | **the human's UUID** — attribution to a person is never severed (D1) |
| `sid` | the **new** session UUID — distinguishes this agent session in every audit row via the existing `sid` plumbing, zero audit-schema change |
| `act` | `{"sub": "agent:<agent_id>"}` — RFC 8693-style actor claim: *who is acting* for the human |
| `aud` | the requested **subset** of the deployment's audience array (D6's free half of scope-down) |
| `iss` | see D7 (§3) |
| `exp` / `iat` | ttl-capped; `exp` never exceeds `SESSION_TOKEN_MAX_TTL` |
| `typ` | `"asunset-session"` — lets validators and audit distinguish session tokens from login tokens |

## 2. Enforcement — intersection at the Authorizer (ratified semantics)

The token is **never a self-sufficient credential**. On mint:

1. An `agent_session:<session_id>` FGA object is written with the declared grant tuples, each carrying a **conditional tuple** `valid_until = expires_at` evaluated at check time.
2. The mint is **audited** (`session.minted`, actor = the human, payload = agent_id/audiences/ttl/label — grants summarized, label redacted through the Redactor port).

At request time, when a resource server presents a principal whose token has `typ=asunset-session`:

```
allowed = check(user:<sub>,               relation, object)   # the human's LIVE permission
      AND check(agent_session:<sid>,      relation, object)   # the session's declared subset
```

Consequences (all ratified, now mechanical):
- **Effective permission = session subset ∩ human's live permissions.** Remove the human's access and every derived session dies with them — a scoped token cannot outlive a revocation.
- **Instant revocation** = delete the session's tuples (`DELETE /platform/sessions/{id}`, allowed to the minting human, org admins, and platform_admin). No blocklists, no waiting for `exp`.
- **Time-boxing** rides the FGA condition, not only `exp` — a leaked token past `valid_until` fails the check even if clock-skewed validators would accept `exp`.

New FGA platform type (composed via `build_model`, alongside the feature spec's types):

```
type agent_session
  relations
    define grantee: [user]        # bookkeeping: the human it derives from
    # capability relations are product-model-specific tuples written
    # against this object at mint time; no relations declared here
    # beyond what products' resource types reference.
```

*(Exact modeling of session→resource tuples per product model is an implementation detail of the mint's grant-writer; v1 supports the platform's own relations plus the product's registered resource types.)*

## 3. D7 — signing authority (OPEN, Avi rules)

The fork kestrel flagged: **who signs session tokens?** Token-exchange being absent is a verified negative; the two real options:

### Option A — asunset mints and signs with its own keypair *(recommended)*

`asunset-api` holds an RS256 keypair; session tokens carry `iss = <public base>/platform/sessions`; JWKS served at `GET /platform/sessions/jwks` (unauthenticated, like any JWKS).

- **Pro:** full claim control — `act`, fresh `sid`, per-mint `aud` subsets, `typ` marker are all trivial. The intersection design needs exactly this freedom.
- **Pro:** no Keycloak preview features; Keycloak stays untouched, login flow unchanged.
- **Con:** every resource server now trusts **two issuers** — contract §5 gains an amendment: *validators select the JWKS source by the `iss` claim (Keycloak's for login tokens, asunset's for session tokens); everything else — RS256, five required claims, per-RS `aud` — is identical.* Mechanical for the three OpsRoom validators (the Node MCP included).
- **Con:** key management lands on asunset: keypair generated at init (CLI secrets path), stored like other secrets, rotation via `kid` overlap (serve old+new in JWKS through a grace window). Bounded, well-trodden work.

### Option B — enable Keycloak token-exchange (RFC 8693 preview)

- **Pro:** single issuer forever; zero validator changes.
- **Con:** preview feature (explicit `--features=token-exchange` activation, semantics have shifted across KC releases).
- **Con — the disqualifier:** exchanged tokens can't cleanly carry **per-mint dynamic claims** — a fresh `sid` per agent session, a caller-chosen `act.sub`, an arbitrary `aud` subset chosen at request time. Mappers are static client config, not per-request parameters. We'd end up bending the design to what exchange can express — and the capability-subset half (FGA session object) has to be built asunset-side *anyway*, so B saves far less than it appears.

**Recommendation: A.** The second-issuer cost is one paragraph of contract amendment and a JWKS-by-issuer lookup in three validators; the claim freedom is exactly what D1+D4 need. B trades that freedom for avoiding work we mostly still have to do.

## 4. What does NOT change

- **Login tokens are untouched** — humans authenticate exactly per contract §5/§6.
- **The interim stays sanctioned until the mint ships**: trusted orchestration asserts `agent_id` as per-request metadata (D1). Adoption never waits on this spec (pre-agreed fallback).
- **No service accounts for agents** (D1 corollary) — the mint is the only agent-credential path.
- `Principal` grows two optional fields (`agent_id`, `is_agent_session`) populated from `act`/`typ`; nothing else in the dependency chain changes shape.

## 5. Implementation order

1. Keypair provisioning (CLI secrets + api startup load) and `GET /platform/sessions/jwks`.
2. `POST /platform/sessions` (mint: validate audiences ⊆ deployment array, cap ttl, write FGA session object + conditional tuples, audit, sign).
3. Validation path: accept `iss`-selected JWKS in `_validate_token`; `Principal` gains `agent_id`; audit rows flow unchanged (new `sid` does the work).
4. Authorizer intersection for `typ=asunset-session` principals.
5. `DELETE /platform/sessions/{id}` + `GET /platform/sessions` (list own; admins list all) — revocation + visibility.
6. Tests: mint/validate/intersect/revoke/expire (folds into the JWT phase of the security-path commission).
7. Contract §5/§9 amendment + notify all RS owners (opsroom-api, orchestration, Node MCP).

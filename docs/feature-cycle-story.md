# A Work Story: `opsroom.tables.smart_create`

**What this is:** a narrative worked example of the full feature cycle — product design → access decision → UX → access matrix → build → scope/operate — written to evaluate the *developer and operator experience* of the feature-registration system, not to implement anything. Nothing in this file is built; the feature is fictional but every mechanism named is real (v1 + feat-ops 1–3) or explicitly marked v1.1.

**Companion:** `docs/feature-permissions-spec.md` (the system itself, §10 = the review-consolidated v1.1). A DX-improvement candidate list derived from this story is at the end.

---

## Act 1 — Product design (Monday)

Product looks at usage data: analysts build tables slowly, and half the queue is "can someone make me a table that shows X." The proposal: **Smart Create** — an AI-assisted table builder; describe the table in plain language, the system drafts the definition for review.

Two facts shape everything downstream: it is **expensive** (every use burns LLM tokens) and **powerful** (it writes draft definitions into projects). So from the first design doc this is not a feature "everyone just gets." The doc ends with a section the platform forces into existence: *"Access: TBD — needs a decision record before build."* That sentence is the cycle working — access is a designed thing, not a default.

## Act 2 — The decision record (Tuesday)

Thirty minutes, product + platform in the room, five decisions written down:

- **D1 — Default: nobody.** The manifest entry ships `grants: []` — declared, gated, granted to no one (the runtime-only pattern).
- **D2 — Steady state: a custom role.** `role:table_analyst`, because "may use AI table creation" is a *job function*, not an org rank. Explicitly not a Keycloak realm role — superseded pattern.
- **D3 — Rollout: pilot with one team first.** Two weeks of the Growth team's real workload before the role-wide grant, so cost and quality data exist before scale.
- **D4 — Agents may use it, as their humans.** The deck-builder agent smart-creates on an analyst's behalf via a scoped session whose grant subset includes the feature — never via its own identity (identity contract D1).
- **D5 — Composition rule.** The feature answers *"may this person use Smart Create at all."* It never answers *"in this project"* (the project resource's `can_edit` check) and never *"is this draft table legal"* (the methodology gate). Three checks, three questions, none substitutable.

## Act 3 — UX (Wednesday)

Three states, one per relationship to the feature:

- **Has it:** a "Smart Create" button in the tables toolbar + a palette entry. Inside a project the user can't edit, the button renders but the *project* refuses — with the project-permission error, not a feature error, because the user *has* the feature.
- **Doesn't have it:** the button doesn't exist. No teaser, no lock icon — a deliberate call: this is a permission, not an upsell. The UI reads `useFeatures()` once; while features load, gated chrome stays hidden rather than flashing and 403ing.
- **Frozen** (incident state, v1.1): the button exists but is disabled — "Smart Create is temporarily unavailable." Distinct from not-granted: during an incident users should know it's *paused*, not that they lost access.

## Act 4 — The access matrix (Thursday morning)

One table, signed by product and platform, pasted into the decision record:

| Persona | See button | Draft a table | In project P | Approve the draft | Freeze/config |
|---|---|---|---|---|---|
| `table_analyst` (role) | ✅ | ✅ | only with `can_edit` on P | ❌ (gate's job) | ❌ |
| Growth team member (pilot) | ✅ (pilot phase) | ✅ | same | ❌ | ❌ |
| Plain org member | ❌ | ❌ | — | — | ❌ |
| Org admin | ❌* | ❌* | — | — | ✅ |
| Agent session (analyst's) | n/a | ✅ if session grant ∧ human has it | same | ❌ | ❌ |
| Service account / outsider | ❌ | ❌ | — | — | ❌ |

\* The admin row is the matrix's most useful line: admins do **not** get the feature by rank — they administer it. An admin who wants to use it gets the role like anyone else. That row would not have been written without the matrix exercise.

## Act 5 — Build (Thursday afternoon; it's short, that's the point)

Backend, one day: one manifest entry (`opsroom.tables.smart_create`, `grants: []`), run codegen so `Feature.TABLES_SMART_CREATE` exists in Python and TS, one `require_feature(...)` dependency stacked above the existing project `can_edit` check, then the handler itself. A typo'd key **fails the boot** with the mismatch named — nothing to memorize. Frontend, one day: wrap the button in `has("opsroom.tables.smart_create")` from the generated union. The MCP wrapper does the same check plus its file-scope check, per D5. Nobody touches Keycloak, nobody writes a migration, nobody opens the FGA store.

## Act 6 — Ship and scope (the two months after)

**Week 1 — pilot.** Deploy; reconcile sees the new key, writes *zero* grants (D1). The consumer doctor dry-runs the reconcile and reports clean. An admin grants the feature to the Growth **team** through the runtime-grants API — one audited call, `feature.granted`, who-granted-what-when in the record. *(v1.1 surface; in v1 this step is the wall — which is why the reviews ruled this class of feature waits for v1.1 rather than anyone hand-writing a tuple.)*

**Week 3 — an incident.** Costs spike — a runaway prompt loop. On-call **freezes** the feature: one API call, every check denies *now*, and the grant ledger is intact, so "who had access during the window" is a query, not archaeology. Fixed Friday; **unfreeze**; access returns exactly as it was. Nobody edited a file mid-incident. *(v1.1.)*

**Week 5 — steady state.** Pilot verdict good. `role:table_analyst` joins the manifest grants; admins assign eleven analysts through the role-assignees API (`role.assigned` ×11 in the audit log); the pilot team grant is revoked — idempotent, audited. Six weeks later a compliance question — "why can María use AI table creation?" — is one lookup: runtime role assignment, granted by whom, on which date, under which audit event id.

**Month 6 — retirement.** Smart Create v2 replaces it. Retirement follows the tombstone rule: `enabled: false` first (the sweep removes every grant, loudly), one release cycle as a tombstone, then the key is deleted — and reconcile would have *refused* the deletion while any grant remained.

## What the story proves, honestly

The **build** half is genuinely a day per surface, and access became a *designed artifact* (the matrix) instead of an emergent property of code. The **scope** half — team pilot, role assignment, freeze, the compliance answer — leans on v1.1: weeks 1, 3, and 5 hit the missing runtime surface. A cycle-A feature could run this whole story today by swapping D1/D3 for a manifest default; *this* feature — the kind consumers actually want first — is why v1.1 exists.

---

# DX-improvement candidates derived from this story

Ranked by value-per-effort. None built; under review.

1. **Consumer testing kit** (`asunset_core.testing`) — the biggest real gap. A `StaticAuthorizer` with declarative grants, a `grant_feature()` helper for live-container style, and the documented pytest fixtures the platform suites already use. Without it, consumers either copy the ephemeral-FGA fixture (heavy per test) or hand-mock the port ad hoc (everyone invents a different fake) — the difference between consumers *testing* their gates and *skipping* it.
2. **JSON Schema for `features.yaml`** — minutes of work; editors get autocomplete, inline key/grant validation, hover docs. Errors while typing instead of at boot. The validator already encodes the rules; the schema is a transcription.
3. **Close the codegen loop** — a staleness test that fails any consumer suite when generated files lag the manifest; a pre-commit recipe in the template; and typing the frontend hook against the generated union (`has(key: FeatureKey)`) so a typo'd key in UI code is a compile error.
4. **"Why?" tooling** — v1.1's provenance listing answers the compliance question; developers ask the inverse daily: "why does bob *not* have this locally?" A small `explain` (CLI or debug endpoint) walking the chain — in manifest? enabled? frozen? which userset grants it? is bob in it? Builds naturally on v1.1's listing.
5. **Scaffold the ceremony** — `asunset feature new <key>` (manifest entry + codegen + prints the exact snippets), and a **decision-record template** with the D1–D5 prompts and an empty access matrix, so the design conversation has a fill-in shape. The template is arguably the higher-value half — it produced the admin-row insight above.
6. **`asunset doctor`** (already on the board) — restated as DX: every recent incident (stale issuer env, unauthenticated readiness probe, tailnet URI bug) surfaced as a confusing runtime symptom a preflight would have named in one line.

Explicitly rejected: a combined "super-dependency" for the router chain (explicit deps are idiomatic FastAPI and self-documenting) and any DSL above the manifest (YAML + schema is the right ceiling).

# Feature decision record — <feature key>

*(Copy per feature. The half-hour that produces the admin row. Story:
docs/feature-cycle-story.md; mechanics: docs/adding-a-feature.md.)*

**Feature:** `<domain.verb>` — one sentence on what it gates.
**Why access is designed, not defaulted:** (cost? power? compliance?)

## Decisions

- **D1 — Default:** who gets it on day one? (`organization#member` /
  `organization#admin` / `role:<name>#assignee` / `[]` runtime-only)
- **D2 — Steady state:** rank, job function (custom role), or per-team?
  If a role: name it; who administers membership?
- **D3 — Rollout:** straight to steady state, or pilot (which team, how
  long, what data decides)?
- **D4 — Agents:** may agent sessions use it as their humans? Any
  session-grant restrictions?
- **D5 — Composition:** what does this feature NOT answer? (per-object
  rights → resource relations; artifact legality → the gate; declared
  reach → which scope resolver per resource type?)

## Access matrix (sign before build)

| Persona | See UI | Use it | Scope/reach | Configure/freeze |
|---|---|---|---|---|
| … | | | | |
| Org admin | ❌* | ❌* | — | ✅ |
| Agent session | n/a | session grant ∧ human | same | ❌ |
| Outsider | ❌ | ❌ | — | ❌ |

\* Admins administer; they don't get features by rank. If an admin
needs it, they get the grant like anyone else. (Keep this row.)

## Retirement

Tombstone path when its day comes: `enabled: false` → reconcile sweep →
remove the key (reconcile refuses while grants remain).

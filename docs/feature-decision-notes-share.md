# Feature decision: notes.share

## Feature

- Area: `notes.share`
- Modes: `basic`, `org_wide`
- Capabilities: `notes.share.basic`, `notes.share.org_wide`

## Why Access Is Designed This Way

Sharing is one product area with two modes because the user intent is the same,
but the blast radius is different. Basic sharing targets named users or teams
and is part of ordinary note collaboration, so every org member may use the
capability. Org-wide sharing reaches every member in the organization, so the
default grant is limited to a custom `sharers` role.

Both modes declare reach over `note` resources through `shareable_notes`. The
existing `visible_notes` resolver is intentionally too broad for this area:
viewers can see a note but should not be able to share it onward. In the Notes
app today, share/unshare authority is already modeled as `can_delete`, so
`shareable_notes` resolves notes admitted by that relation and handlers hydrate
only those ids.

## D1: Default Personas

- `notes.share.basic`: `organization#member`
- `notes.share.org_wide`: `role:sharers#assignee`
- Runtime user/team grants remain operator data, not manifest defaults.

## D2: Rollout And Operation

- Reconcile preview must show the new desired default grants before apply.
- Assigning a user to `sharers` grants `notes.share.org_wide` by default.
- `GET /platform/features/{key}/explain?user_id=...` is the operator path for
  proving why a user does or does not have the capability.

## D3: Resource Reach

| Capability | Resource type | Resolver | Rationale |
|---|---|---|---|
| `notes.share.basic` | `note` | `shareable_notes` | User/team sharing still needs share authority on the note. |
| `notes.share.org_wide` | `note` | `shareable_notes` | Org-wide sharing has larger blast radius but the same note-level share authority. |

## D4: Agent/Session Composition

Agent sessions should receive either `notes.share.basic` or
`notes.share.org_wide` explicitly in their session grant subset. The feature
gate is the capability door; `resolve_scope` is the reach door. An agent with
the feature but no `can_delete` reach over notes gets an empty candidate set.

## D5: Consumer Business Logic Contract

The feature model assumes the application composes feature gates with
resource authority. A handler must not infer reachable notes from role names or
membership. It must call `resolve_scope(manifest, key, "note", principal,
authorizer)` and use those ids as the only DB selector for note objects. Any
lifecycle predicate, payload validation, audit rule, or write semantics stays
in the Notes app business logic, after the resolver has supplied the object
set.

## Access Matrix Rows

| Capability | Default personas | Declared reach | UI state |
|---|---|---|---|
| `notes.share.basic` | `organization#member` | `note -> shareable_notes` | Show user/team share controls. |
| `notes.share.org_wide` | `role:sharers#assignee` | `note -> shareable_notes` | Show org-wide share control. |

## Retirement

Disable a mode with `enabled: false`, run feature reconcile, and leave the
area vocabulary intact until all consumers and docs stop referencing the mode.
If the whole area retires, remove the feature rows, regenerate constants,
matrix, and skeletons, then prune orphaned runtime grants through the feature
operations surface.

## Self-Assessment

The matrix mental model is useful here as an authored design artifact because
it exposes two axes that matter to consumers: persona default grant and
resource reach. It is not the enforcement model. Enforcement is still
composition: `require_feature` for the capability, `resolve_scope` for reach,
then ordinary app business logic for payload and lifecycle rules.

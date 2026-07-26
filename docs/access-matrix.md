<!-- GENERATED from features.yaml — do not edit; re-run asunset_core.features.matrix -->
# Access matrix (design-time projection)

Runtime grants legitimately diverge from this (per-user/team grants,
freezes) — the runtime truth is GET /platform/features; the diff
between the two is a compliance REPORT, never a gate.

| Capability | State | Default personas | Declared reach | UI state |
|---|---|---|---|---|
| `audit.view` | enabled | organization#member | *undeclared (grandfathered)* | _(design column)_ |
| `notes.export` | enabled | organization#member | note → visible_notes | _(design column)_ |
| `notes.archive` | enabled | role:archivists#assignee | *undeclared (grandfathered)* | _(design column)_ |
| `notes.share.basic` | enabled | organization#member | note → shareable_notes | _(design column)_ |
| `notes.share.org_wide` | enabled | role:sharers#assignee | note → shareable_notes | _(design column)_ |

## Areas (declared mode vocabularies)

- `notes.share`: basic, org_wide

# Runbook: freeze a feature during an incident

**When:** a feature is misbehaving in a way that burns money, data, or
trust (runaway AI loop, abuse of an export path) and you need it
stopped NOW, reversibly, without losing the record of who had access.

**What freeze does:** every gated request for that feature denies
immediately ("temporarily unavailable"); **all grants are preserved**;
one call reverses it. This is NOT `enabled: false` in the manifest —
that is decommission (destructive sweep, deploy-time, grants don't come
back). Freeze is the incident tool; decommission is the retirement tool.

## The command (token custody pre-solved)

SSH to the deployment box (over the tailnet), then from the deployment
root (where `.env` lives):

    tools/ops/feature-freeze.sh freeze notes.export "cost spike INC-123"
    tools/ops/feature-freeze.sh status
    tools/ops/feature-freeze.sh unfreeze notes.export

No human token juggling: the script authenticates as the **machine
operator identity** — the asunset-api service account (holds
`platform_support`; its client credentials are the box's own `.env`).
The response states **blast radius** ("frozen: [notes.export]") — read
it; a freeze that surprised you is a second incident.

## After the incident

- The freeze/unfreeze events are in the audit trail
  (`feature.frozen` / `feature.unfrozen`, with reason and actor).
- "Who had access during the window" is a query against the grant
  bookkeeping (`GET /platform/features` shows grants with provenance) —
  the ledger was preserved, that's the point of freeze.
- If the feature is being retired for good, follow the tombstone path:
  `enabled: false` in the manifest → reconcile (sweeps) → remove the key.

## Failure modes

- `403 operator role required` — the service account lacks
  `platform_support`: run keycloak-init (or check it ran) on this
  deployment; the grant is applied on every init.
- Token request fails — check `KEYCLOAK_INTERNAL_URL` mapping (script
  defaults `keycloak:8080` → `localhost:8080` on-box) and the client
  secret in `.env`.
- `422 unknown feature` — key typo'd; run `status` to list keys.

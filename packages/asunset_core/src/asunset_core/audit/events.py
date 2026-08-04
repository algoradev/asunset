"""Audit event schema.

Event types are a closed vocabulary defined here. Payload is a free-form
dict but each event type should document its expected shape inline where
it's emitted — schema-by-convention rather than schema-by-validation so
the log record evolves faster than migrations, which is what HIPAA auditors
actually want (they read payloads, not dataclasses).
"""

from __future__ import annotations

import enum


class EventType(str, enum.Enum):
    # Identity (echoed from Keycloak for the app-local record)
    USER_FIRST_SEEN = "user.first_seen"

    # Notes
    NOTE_CREATED = "note.created"
    NOTE_VIEWED = "note.viewed"
    NOTE_UPDATED = "note.updated"
    NOTE_DELETED = "note.deleted"
    NOTE_SHARED = "note.shared"
    NOTE_UNSHARED = "note.unshared"

    # Org / Team
    ORG_CREATED = "org.created"
    ORG_MEMBER_ADDED = "org.member_added"
    ORG_MEMBER_REMOVED = "org.member_removed"
    ORG_MEMBER_ROLE_CHANGED = "org.member_role_changed"
    # Invite lifecycle. ORG_MEMBER_INVITED is the "I just sent a magic
    # link" event; ORG_MEMBER_ADDED still fires only when the user has
    # accepted (verified email), so the two are not redundant.
    ORG_MEMBER_INVITED = "org.member_invited"
    ORG_INVITE_RESENT = "org.invite_resent"
    ORG_INVITE_REVOKED = "org.invite_revoked"
    TEAM_CREATED = "team.created"
    TEAM_RENAMED = "team.renamed"
    TEAM_DELETED = "team.deleted"
    TEAM_MEMBER_ADDED = "team.member_added"
    TEAM_MEMBER_REMOVED = "team.member_removed"
    TEAM_MEMBER_ROLE_CHANGED = "team.member_role_changed"

    # Feature-registration lifecycle (feature spec / feat-ops).
    FEATURES_RECONCILED = "features.reconciled"
    FEATURE_GRANTED = "feature.granted"
    FEATURE_REVOKED = "feature.revoked"
    FEATURE_FROZEN = "feature.frozen"
    FEATURE_UNFROZEN = "feature.unfrozen"
    ROLE_ASSIGNED = "role.assigned"
    ROLE_UNASSIGNED = "role.unassigned"

    # Agent sessions (D4 mint) — lifecycle of scoped, attributable
    # agent credentials derived from a human login.
    SESSION_MINTED = "session.minted"
    SESSION_REVOKED = "session.revoked"

    # Authorization outcomes (supplements OpenFGA's own decision logs with
    # app-level context — same request, the app's interpretation).
    ACCESS_DENIED = "access.denied"

    # FGA reconciliation — emitted by the reconcile job / endpoint.
    # Threshold these in SIEM: bursts of drift suggest a bug or an attack
    # (someone bypassed the dual-write ordering) and warrant investigation.
    FGA_RECONCILE_RUN = "fga.reconcile_run"
    FGA_DRIFT_DETECTED = "fga.drift_detected"
    FGA_DRIFT_FIXED = "fga.drift_fixed"

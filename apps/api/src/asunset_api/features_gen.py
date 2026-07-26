"""GENERATED from features.yaml — do not edit; re-run asunset_core.features.codegen"""

from enum import StrEnum


class Feature(StrEnum):
    AUDIT_VIEW = "audit.view"  # Read the org's audit trail in the in-app viewer
    NOTES_EXPORT = "notes.export"  # Export visible notes as CSV
    NOTES_ARCHIVE = "notes.archive"  # Archive notes without deleting them
    NOTES_SHARE_BASIC = "notes.share.basic"  # Share notes with users and teams
    NOTES_SHARE_ORG_WIDE = "notes.share.org_wide"  # Share notes to the whole organization


FEATURE_AREAS = {
    "notes.share": ['basic', 'org_wide'],
}

CAPABILITIES_BY_AREA = {
    "notes.share": ['notes.share.basic', 'notes.share.org_wide'],
}

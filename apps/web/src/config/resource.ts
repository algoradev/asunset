import { FileText, type LucideIcon } from "lucide-react";

// The single domain resource this product exposes (Note in the template,
// Report / Invoice / Case / etc. in a consumer fork).
//
// Two fields stay as code because they can't come from string env vars:
//   - `routeKey` drives the `Route` type union (literal-typed).
//   - `icon` is a Lucide React component, not a string.
//
// Everything else is env-driven (VITE_RESOURCE_*), so consumers rebrand
// labels via the root `.env` without editing this file. Falls back to
// the Notes-demo defaults if env is unset.
//
// Fields tied to the resource's schema (title, body, team_id) are *not*
// config — see NewNoteDialog / NoteDetailDialog, which the consumer is
// expected to rewrite when their resource has different columns.
export const RESOURCE = {
  routeKey: "notes",
  icon: FileText as LucideIcon,
  name: import.meta.env.VITE_RESOURCE_NAME || "Note",
  plural: import.meta.env.VITE_RESOURCE_PLURAL || "Notes",
  newLabel: import.meta.env.VITE_RESOURCE_NEW_LABEL || "New note",
  emptyLabel:
    import.meta.env.VITE_RESOURCE_EMPTY_LABEL || "No notes in this view.",
  shareDialogDescription:
    import.meta.env.VITE_RESOURCE_SHARE_DESC ||
    "Grant access to a user, a team, or the whole organization.",
} as const;

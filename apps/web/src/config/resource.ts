import { FileText, type LucideIcon } from "lucide-react";

// The single domain resource this product exposes (Note in the template,
// Report / Invoice / Case / etc. in a consumer fork). Changing `routeKey`
// propagates through the Route type union, URL hash, and sidebar item.
//
// Fields tied to the resource's schema (title, body, team_id) are *not*
// config — see NewNoteDialog / NoteDetailDialog, which the consumer is
// expected to rewrite when their resource has different columns.
export const RESOURCE = {
  routeKey: "notes",
  name: "Note",
  plural: "Notes",
  newLabel: "New note",
  icon: FileText as LucideIcon,
  emptyLabel: "No notes in this view.",
  shareDialogDescription:
    "Grant access to a user, a team, or the whole organization.",
} as const;

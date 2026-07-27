/**
 * Typed API client. Transport is the SDK fetch core (bearer +
 * X-Correlation-Id on every request, ApiError with the server-echoed
 * correlation id); the platform surface is the SDK's Tier-2a client.
 * This file owns only the PRODUCT endpoints (the Notes demo) and merges
 * both behind the one `api` object feature code already imports.
 */

import { createApiCore, createPlatformClient } from "@asunset/web-sdk";
import type { Fetcher } from "@asunset/web-sdk";

// Re-exported so feature code keeps one import site for API concerns.
export { ApiError } from "@asunset/web-sdk";
export type { Fetcher };
export type {
  AuditEvent,
  InviteDelivery,
  InviteResendResult,
  InviteResult,
  Me,
  Org,
  OrgMember,
  ReconcileReport,
  Role,
  Team,
  TeamMember,
  User,
} from "@asunset/web-sdk";

const core = createApiCore(import.meta.env.VITE_API_URL);
const request = core.request;
const requestText = core.requestText;
const platform = createPlatformClient(core);

// --- Types (mirror the Pydantic schemas) ---

export type Relation = "viewer" | "editor";

export type Note = {
  id: string;
  title: string;
  body: string;
  owner_id: string;
  team_id: string | null;
  created_at: string;
  updated_at: string;
  // How the current caller sees this note: owner | direct:{relation} |
  // team '<name>' as <relation> | organization '<name>' as <relation> | unknown
  access_path: string | null;
};

export type NoteScope = "mine" | "team" | "shared" | "org";

export type ShareBody =
  | { user_id: string; relation: Relation }
  | { team_id: string; relation: Relation }
  | { org: true; relation: Relation };

export type NoteGrant = {
  kind: "user" | "team" | "org";
  relation: Relation;
  user_id: string | null;
  team_id: string | null;
  org_id: string | null;
  label: string | null;
  email: string | null;
};

// --- Endpoints: the platform surface spreads in from the SDK; this
// object adds the product (Notes) endpoints on top. ---

export const api = {
  ...platform,

  // notes
  listNotes: (f: Fetcher, scope: NoteScope, teamId?: string) => {
    const qs = new URLSearchParams({ scope });
    if (teamId) qs.set("team_id", teamId);
    return request<Note[]>(`/notes?${qs.toString()}`, {}, f);
  },
  getNote: (f: Fetcher, id: string) =>
    request<Note>(`/notes/${id}`, {}, f),
  createNote: (
    f: Fetcher,
    body: { title: string; body: string; team_id?: string | null },
  ) =>
    request<Note>("/notes", { method: "POST", body: JSON.stringify(body) }, f),
  updateNote: (
    f: Fetcher,
    id: string,
    body: { title?: string; body?: string },
  ) =>
    request<Note>(
      `/notes/${id}`,
      { method: "PATCH", body: JSON.stringify(body) },
      f,
    ),
  deleteNote: (f: Fetcher, id: string) =>
    request<void>(`/notes/${id}`, { method: "DELETE" }, f),
  shareNote: (f: Fetcher, id: string, body: ShareBody) =>
    request<unknown>(
      `/notes/${id}/shares`,
      { method: "POST", body: JSON.stringify(body) },
      f,
    ),
  unshareNote: (f: Fetcher, id: string, body: ShareBody) =>
    request<void>(
      `/notes/${id}/shares`,
      { method: "DELETE", body: JSON.stringify(body) },
      f,
    ),
  listNoteShares: (f: Fetcher, id: string) =>
    request<NoteGrant[]>(`/notes/${id}/shares`, {}, f),
  exportNotesCsv: (f: Fetcher) => requestText("/notes/export", {}, f),
};

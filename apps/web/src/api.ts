/**
 * Typed API client.
 *
 * Injects the Keycloak access token as Bearer on every request, plus a
 * freshly-minted X-Correlation-Id so the FastAPI correlation middleware
 * (and every downstream log line) can tie this browser action to the
 * same trace_id the SIEM sees.
 */

const API_URL = import.meta.env.VITE_API_URL;

function newCorrelationId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(12)))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly correlationId: string,
  ) {
    super(message);
  }
}

export type Fetcher = {
  accessToken: string | undefined;
};

async function request<T>(
  path: string,
  init: RequestInit,
  { accessToken }: Fetcher,
): Promise<T> {
  const correlationId = newCorrelationId();
  const headers = new Headers(init.headers);
  headers.set("X-Correlation-Id", correlationId);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const resp = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new ApiError(
      resp.status,
      text || resp.statusText,
      resp.headers.get("X-Correlation-Id") ?? correlationId,
    );
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

// --- Types (mirror the Pydantic schemas) ---

export type Role = "admin" | "member";
export type Relation = "viewer" | "editor";

export type User = {
  id: string;
  email: string;
  display_name: string;
};

export type Me = {
  user: User;
  realm_roles: string[];
  org_id: string | null;
  org_role: Role | null;
};

export type Org = {
  id: string;
  name: string;
  created_at: string;
};

export type OrgMember = {
  user: User;
  role: Role;
  joined_at: string;
};

export type Team = {
  id: string;
  name: string;
  created_at: string;
};

export type TeamMember = {
  user: User;
  role: Role;
  joined_at: string;
};

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

export type AuditEvent = {
  id: string;
  timestamp: string;
  actor_id: string | null;
  actor_email: string | null;
  actor_display_name: string | null;
  actor_org_role: "admin" | "member" | null;
  actor_realm_roles: string[];
  trace_id: string | null;
  event_type: string;
  resource_type: string | null;
  resource_id: string | null;
  resource_label: string | null;
  action: string;
  permission: string | null;
  permission_path: string | null;
  source_ip: string | null;
  user_agent: string | null;
  session_id: string | null;
  success: boolean;
  payload: Record<string, unknown>;
};

export type ReconcileReport = {
  checked: number;
  missing_tuples: number;
  added_tuples: number;
  drift_by_type: Record<string, number>;
};

export type ShareBody =
  | { user_id: string; relation: Relation }
  | { team_id: string; relation: Relation }
  | { org: true; relation: Relation };

// --- Endpoints ---

export const api = {
  // platform
  me: (f: Fetcher) => request<Me>("/platform/me", {}, f),
  bootstrap: (f: Fetcher, body: { org_name: string }) =>
    request<{ org_id: string }>(
      "/platform/bootstrap",
      { method: "POST", body: JSON.stringify(body) },
      f,
    ),
  reconcileFga: (f: Fetcher) =>
    request<ReconcileReport>(
      "/platform/reconcile-fga",
      { method: "POST" },
      f,
    ),

  // users
  lookupUser: (f: Fetcher, email: string) =>
    request<User>(
      "/users/lookup",
      { method: "POST", body: JSON.stringify({ email }) },
      f,
    ),

  // org
  getOrg: (f: Fetcher) => request<Org>("/orgs/current", {}, f),
  listOrgMembers: (f: Fetcher) =>
    request<OrgMember[]>("/orgs/current/members", {}, f),
  addOrgMember: (f: Fetcher, body: { user_id: string; role: Role }) =>
    request<OrgMember>(
      "/orgs/current/members",
      { method: "POST", body: JSON.stringify(body) },
      f,
    ),
  removeOrgMember: (f: Fetcher, user_id: string) =>
    request<void>(
      `/orgs/current/members/${user_id}`,
      { method: "DELETE" },
      f,
    ),

  // teams
  listTeams: (f: Fetcher) => request<Team[]>("/teams", {}, f),
  createTeam: (f: Fetcher, body: { name: string }) =>
    request<Team>(
      "/teams",
      { method: "POST", body: JSON.stringify(body) },
      f,
    ),
  deleteTeam: (f: Fetcher, id: string) =>
    request<void>(`/teams/${id}`, { method: "DELETE" }, f),
  listTeamMembers: (f: Fetcher, id: string) =>
    request<TeamMember[]>(`/teams/${id}/members`, {}, f),
  addTeamMember: (
    f: Fetcher,
    id: string,
    body: { user_id: string; role: Role },
  ) =>
    request<TeamMember>(
      `/teams/${id}/members`,
      { method: "POST", body: JSON.stringify(body) },
      f,
    ),
  removeTeamMember: (f: Fetcher, teamId: string, userId: string) =>
    request<void>(
      `/teams/${teamId}/members/${userId}`,
      { method: "DELETE" },
      f,
    ),

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

  // audit
  listAuditEvents: (
    f: Fetcher,
    filters: {
      limit?: number;
      event_type?: string;
      actor_id?: string;
      trace_id?: string;
      since?: string;
      until?: string;
    } = {},
  ) => {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    });
    return request<AuditEvent[]>(
      `/audit/events${qs.toString() ? `?${qs.toString()}` : ""}`,
      {},
      f,
    );
  },
};

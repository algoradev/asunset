/**
 * Tier 2a — the typed platform client. Framework-free: plain functions
 * over the Tier-1 fetch core, safe from any state layer (raw
 * useState/useEffect, TanStack, whatever the consumer runs).
 *
 * Types mirror asunset_api's Pydantic schemas; endpoint paths are the
 * platform routers every consumer mounts. Product resources (the Notes
 * demo etc.) stay in the consumer's own client — this file is platform
 * surface only.
 */

import type { ApiCore, Fetcher } from "./fetch";

// --- Platform types ---

export type Role = "admin" | "member";

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
  // True when the member hasn't accepted their magic-link invite yet
  // (Keycloak `emailVerified=false`). Only populated for org admins;
  // for regular members the backend always returns `false`.
  pending: boolean;
};

export type InviteDelivery = "magic_link" | "temporary_password" | "none";

export type InviteResult = {
  member: OrgMember;
  delivery: InviteDelivery;
  was_new_user: boolean;
  // Returned exactly once when delivery === "temporary_password".
  // The consumer UI must surface it; it isn't recoverable afterward.
  temporary_password: string | null;
};

export type InviteResendResult = {
  delivery: InviteDelivery;
  temporary_password: string | null;
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

export type AuditEvent = {
  id: string;
  timestamp: string;
  actor_id: string | null;
  actor_email: string | null;
  actor_display_name: string | null;
  actor_org_role: Role | null;
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

export type AuditFilters = {
  limit?: number;
  event_type?: string;
  actor_id?: string;
  trace_id?: string;
  since?: string;
  until?: string;
};

// --- The client ---

export type PlatformClient = ReturnType<typeof createPlatformClient>;

export function createPlatformClient(core: ApiCore) {
  const { request } = core;
  return {
    // platform
    me: (f: Fetcher) => request<Me>("/platform/me", {}, f),
    // Feature keys the caller may use — drives menu/route gating (UX
    // only; the API-side require_feature check is the control).
    meFeatures: (f: Fetcher) =>
      request<string[]>("/platform/me/features", {}, f),
    bootstrap: (f: Fetcher, body: { org_name: string }) =>
      request<{ org_id: string }>(
        "/platform/bootstrap",
        { method: "POST", body: JSON.stringify(body) },
        f,
      ),
    reconcileFga: (f: Fetcher) =>
      request<ReconcileReport>("/platform/reconcile-fga", { method: "POST" }, f),

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
    updateOrgMemberRole: (f: Fetcher, user_id: string, role: Role) =>
      request<OrgMember>(
        `/orgs/current/members/${user_id}`,
        { method: "PATCH", body: JSON.stringify({ role }) },
        f,
      ),
    removeOrgMember: (f: Fetcher, user_id: string) =>
      request<void>(
        `/orgs/current/members/${user_id}`,
        { method: "DELETE" },
        f,
      ),
    inviteOrgMember: (f: Fetcher, body: { email: string; role: Role }) =>
      request<InviteResult>(
        "/orgs/current/invites",
        { method: "POST", body: JSON.stringify(body) },
        f,
      ),
    resendOrgInvite: (f: Fetcher, user_id: string) =>
      request<InviteResendResult>(
        `/orgs/current/invites/${user_id}/resend`,
        { method: "POST" },
        f,
      ),
    revokeOrgInvite: (f: Fetcher, user_id: string) =>
      request<void>(
        `/orgs/current/invites/${user_id}`,
        { method: "DELETE" },
        f,
      ),

    // teams
    listTeams: (f: Fetcher) => request<Team[]>("/teams", {}, f),
    createTeam: (f: Fetcher, body: { name: string }) =>
      request<Team>("/teams", { method: "POST", body: JSON.stringify(body) }, f),
    renameTeam: (f: Fetcher, id: string, body: { name: string }) =>
      request<Team>(
        `/teams/${id}`,
        { method: "PATCH", body: JSON.stringify(body) },
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
    updateTeamMemberRole: (
      f: Fetcher,
      teamId: string,
      userId: string,
      role: Role,
    ) =>
      request<TeamMember>(
        `/teams/${teamId}/members/${userId}`,
        { method: "PATCH", body: JSON.stringify({ role }) },
        f,
      ),
    removeTeamMember: (f: Fetcher, teamId: string, userId: string) =>
      request<void>(
        `/teams/${teamId}/members/${userId}`,
        { method: "DELETE" },
        f,
      ),

    // audit
    listAuditEvents: (f: Fetcher, filters: AuditFilters = {}) => {
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
}

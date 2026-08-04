/**
 * Tier 2b — headless platform hooks over @tanstack/react-query.
 *
 * OPT-IN: this module is a separate entry (`@asunset/web-sdk/hooks`) so
 * consumers who don't run TanStack never resolve it — the kernel and
 * the 2a client stay state-library-free. Import from here only if
 * @tanstack/react-query (^5) is in your app.
 *
 * The hooks own what's expensive to get wrong — query keys, cache
 * invalidation, the composite flows (email→lookup→add, resend carrying
 * the recipient email through), enabled-gating on the token — and own
 * nothing about presentation: no i18n, no toasts, no copy. Pass
 * `onSuccess`/`onError` callbacks for your UI reactions; invalidations
 * run regardless, before your callback.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  AuditEvent,
  AuditFilters,
  InviteResendResult,
  InviteResult,
  Me,
  Org,
  OrgMember,
  PlatformClient,
  ReconcileReport,
  Role,
  Team,
  TeamMember,
} from "./platform";
import { useFetcher } from "./provider";

/**
 * The canonical query-key registry. Consumers invalidate through these,
 * never through hand-typed string literals (the drift the registry
 * exists to kill).
 */
export const platformKeys = {
  me: ["platform", "me"] as const,
  meFeatures: ["platform", "me-features"] as const,
  org: ["platform", "org"] as const,
  orgMembers: ["platform", "org-members"] as const,
  teams: ["platform", "teams"] as const,
  teamMembers: (teamId: string) =>
    ["platform", "team-members", teamId] as const,
  audit: (filters: AuditFilters) => ["platform", "audit", filters] as const,
};

/** UI-reaction callbacks — presentation stays yours. */
export type MutationCallbacks<TData, TVars> = {
  onSuccess?: (data: TData, vars: TVars) => void;
  onError?: (error: Error, vars: TVars) => void;
};

export function createPlatformHooks(client: PlatformClient) {
  function usePlatformQuery<T>(
    key: readonly unknown[],
    fn: (f: { accessToken: string | undefined }) => Promise<T>,
    opts?: { staleTime?: number; enabled?: boolean },
  ) {
    const f = useFetcher();
    return useQuery({
      queryKey: key,
      queryFn: () => fn(f),
      enabled: (opts?.enabled ?? true) && !!f.accessToken,
      staleTime: opts?.staleTime,
    });
  }

  function usePlatformMutation<TData, TVars>(
    run: (
      f: { accessToken: string | undefined },
      vars: TVars,
    ) => Promise<TData>,
    invalidates: (vars: TVars) => readonly (readonly unknown[])[],
    cb?: MutationCallbacks<TData, TVars>,
  ) {
    const f = useFetcher();
    const qc = useQueryClient();
    return useMutation<TData, Error, TVars>({
      mutationFn: (vars) => run(f, vars),
      onSuccess: (data, vars) => {
        for (const key of invalidates(vars)) {
          void qc.invalidateQueries({ queryKey: key });
        }
        cb?.onSuccess?.(data, vars);
      },
      onError: (e, vars) => cb?.onError?.(e, vars),
    });
  }

  return {
    // --- queries ---
    useMe: () => usePlatformQuery<Me>(platformKeys.me, (f) => client.me(f)),
    useOrg: (opts?: { staleTime?: number }) =>
      usePlatformQuery<Org>(platformKeys.org, (f) => client.getOrg(f), opts),
    useOrgMembers: (opts?: { staleTime?: number; enabled?: boolean }) =>
      usePlatformQuery<OrgMember[]>(
        platformKeys.orgMembers,
        (f) => client.listOrgMembers(f),
        opts,
      ),
    useTeams: () =>
      usePlatformQuery<Team[]>(platformKeys.teams, (f) => client.listTeams(f)),
    useTeamMembers: (teamId: string) =>
      usePlatformQuery<TeamMember[]>(platformKeys.teamMembers(teamId), (f) =>
        client.listTeamMembers(f, teamId),
      ),
    useAudit: (filters: AuditFilters) =>
      usePlatformQuery<AuditEvent[]>(platformKeys.audit(filters), (f) =>
        client.listAuditEvents(f, filters),
      ),

    /**
     * Feature keys the signed-in user may use. UX gating only — hide
     * menu items and routes with it; the API-side require_feature check
     * is the control. Generic over your generated FeatureKey union so a
     * typo'd key is a COMPILE error:
     *
     *   const { has } = useFeatureSet<FeatureKey>();
     */
    useFeatureSet<K extends string = string>() {
      const q = usePlatformQuery<string[]>(
        platformKeys.meFeatures,
        (f) => client.meFeatures(f),
        { staleTime: 60_000 },
      );
      const set = new Set(q.data ?? []);
      return {
        features: set,
        has: (key: K) => set.has(key),
        isLoading: q.isLoading,
      };
    },

    // --- mutations ---
    useBootstrap: (cb?: MutationCallbacks<{ org_id: string }, { org_name: string }>) =>
      usePlatformMutation(
        (f, vars) => client.bootstrap(f, vars),
        () => [platformKeys.me],
        cb,
      ),
    useReconcileFga: (cb?: MutationCallbacks<ReconcileReport, void>) =>
      usePlatformMutation((f) => client.reconcileFga(f), () => [], cb),

    useInviteMember: (
      cb?: MutationCallbacks<InviteResult, { email: string; role: Role }>,
    ) =>
      usePlatformMutation(
        (f, vars) => client.inviteOrgMember(f, vars),
        () => [platformKeys.orgMembers],
        cb,
      ),
    /**
     * Resend carries the recipient email through to onSuccess so the UI
     * can attribute the (possibly one-time temp-password) result without
     * re-deriving it — the composite the reference app proved necessary.
     */
    useResendInvite: (
      cb?: MutationCallbacks<
        { result: InviteResendResult; email: string },
        { userId: string; email: string }
      >,
    ) =>
      usePlatformMutation(
        async (f, vars) => ({
          result: await client.resendOrgInvite(f, vars.userId),
          email: vars.email,
        }),
        () => [],
        cb,
      ),
    useRevokeInvite: (cb?: MutationCallbacks<void, { userId: string }>) =>
      usePlatformMutation(
        (f, vars) => client.revokeOrgInvite(f, vars.userId),
        () => [platformKeys.orgMembers],
        cb,
      ),
    useUpdateOrgMemberRole: (
      cb?: MutationCallbacks<OrgMember, { userId: string; newRole: Role }>,
    ) =>
      usePlatformMutation(
        (f, vars) => client.updateOrgMemberRole(f, vars.userId, vars.newRole),
        () => [platformKeys.orgMembers],
        cb,
      ),
    useRemoveOrgMember: (cb?: MutationCallbacks<void, { userId: string }>) =>
      usePlatformMutation(
        (f, vars) => client.removeOrgMember(f, vars.userId),
        () => [platformKeys.orgMembers],
        cb,
      ),

    useCreateTeam: (cb?: MutationCallbacks<Team, { name: string }>) =>
      usePlatformMutation(
        (f, vars) => client.createTeam(f, vars),
        () => [platformKeys.teams],
        cb,
      ),
    useRenameTeam: (
      cb?: MutationCallbacks<Team, { teamId: string; name: string }>,
    ) =>
      usePlatformMutation(
        (f, vars) => client.renameTeam(f, vars.teamId, { name: vars.name }),
        () => [platformKeys.teams],
        cb,
      ),
    useDeleteTeam: (cb?: MutationCallbacks<void, { teamId: string }>) =>
      usePlatformMutation(
        (f, vars) => client.deleteTeam(f, vars.teamId),
        () => [platformKeys.teams],
        cb,
      ),
    /**
     * The email→lookup→add composite as ONE mutation, so consumers
     * can't half-implement it (lookup without add, add by unchecked id).
     */
    useAddTeamMember: (
      cb?: MutationCallbacks<
        TeamMember,
        { teamId: string; email: string; role: Role }
      >,
    ) =>
      usePlatformMutation(
        async (f, vars) => {
          const user = await client.lookupUser(f, vars.email);
          return client.addTeamMember(f, vars.teamId, {
            user_id: user.id,
            role: vars.role,
          });
        },
        (vars) => [platformKeys.teamMembers(vars.teamId)],
        cb,
      ),
    useUpdateTeamMemberRole: (
      cb?: MutationCallbacks<
        TeamMember,
        { teamId: string; userId: string; newRole: Role }
      >,
    ) =>
      usePlatformMutation(
        (f, vars) =>
          client.updateTeamMemberRole(f, vars.teamId, vars.userId, vars.newRole),
        (vars) => [platformKeys.teamMembers(vars.teamId)],
        cb,
      ),
    useRemoveTeamMember: (
      cb?: MutationCallbacks<void, { teamId: string; userId: string }>,
    ) =>
      usePlatformMutation(
        (f, vars) => client.removeTeamMember(f, vars.teamId, vars.userId),
        (vars) => [platformKeys.teamMembers(vars.teamId)],
        cb,
      ),
  };
}

export type PlatformHooks = ReturnType<typeof createPlatformHooks>;

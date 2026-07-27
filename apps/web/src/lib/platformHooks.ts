// The app's Tier-2b hooks instance — query keys, cache invalidation,
// and the composite flows live in the SDK; pages import from here and
// keep only their own toasts/i18n/UI state.
import { createPlatformHooks } from "@asunset/web-sdk/hooks";

import { platform } from "@/api";

export const {
  useMe,
  useOrg,
  useOrgMembers,
  useTeams,
  useTeamMembers,
  useAudit,
  useFeatureSet,
  useBootstrap,
  useReconcileFga,
  useInviteMember,
  useResendInvite,
  useRevokeInvite,
  useUpdateOrgMemberRole,
  useRemoveOrgMember,
  useCreateTeam,
  useDeleteTeam,
  useAddTeamMember,
  useUpdateTeamMemberRole,
  useRemoveTeamMember,
} = createPlatformHooks(platform);

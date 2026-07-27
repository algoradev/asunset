/**
 * @asunset/web-sdk — the asunset browser auth kernel (Tier 1).
 *
 * Contract (docs/frontend-sdk-decision.md): if a browser surface does
 * auth against asunset identity, it does it through this package —
 * hand-rolled OIDC/token handling is a review-blocker. Headless by
 * design: no components, no i18n, no styling; consumers own all pixels.
 */

export { createOidcConfig } from "./config";
export type { AsunsetOidcConfig, OidcConfigOptions } from "./config";

export { AsunsetAuthProvider, useFetcher } from "./provider";

export { useSilentBootstrap } from "./bootstrap";
export type { SilentBootstrapState } from "./bootstrap";

export { useIdleLogout } from "./idle";
export type { IdleLogoutOptions, IdleState } from "./idle";

export { ApiError, authHeaders, createApiCore, newCorrelationId } from "./fetch";
export type { ApiCore, Fetcher } from "./fetch";

export { runSilentRenewCallback } from "./silent-renew";

// Tier 2a — typed platform client (framework-free).
export { createPlatformClient } from "./platform";
export type {
  AuditEvent,
  AuditFilters,
  InviteDelivery,
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
  User,
} from "./platform";

// Re-exported so consumers don't import react-oidc-context directly for
// the everyday hook (one named seam; the peer dep stays theirs to declare).
export { useAuth } from "react-oidc-context";

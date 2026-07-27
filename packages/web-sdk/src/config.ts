import type { AuthProviderProps } from "react-oidc-context";
import type { UserManagerSettings } from "oidc-client-ts";
import { InMemoryWebStorage, WebStorageStateStore } from "oidc-client-ts";

/**
 * AuthProviderProps is a union (settings-props vs bring-your-own
 * UserManager); the intersection keeps the concrete settings fields
 * visible to consumers and tests.
 */
export type AsunsetOidcConfig = AuthProviderProps & UserManagerSettings;

/**
 * Inputs for the asunset OIDC client config. All values are explicit —
 * the SDK never reads build-time env itself (contract guard: env flows
 * through factories, so a consumer can source these from wherever their
 * stack keeps config).
 */
export type OidcConfigOptions = {
  /** Public Keycloak base URL as browsers see it (issuer host). */
  keycloakUrl: string;
  realm: string;
  clientId: string;
  /** Defaults to `window.location.origin`. */
  redirectUri?: string;
  /** Defaults to `redirectUri`. */
  postLogoutRedirectUri?: string;
  /**
   * Where the silent-renew page is served on YOUR origin. Defaults to
   * `/silent-renew.html`. The page must exist (see `runSilentRenewCallback`
   * and the package README) — silent renew is what makes the in-memory
   * token posture survive reloads.
   */
  silentRenewPath?: string;
};

/**
 * The asunset browser auth posture (A7), as react-oidc-context props.
 *
 * Token-storage contract: tokens live IN MEMORY ONLY — nothing in
 * localStorage/sessionStorage, so no token survives XSS-adjacent storage
 * reads or lands in backups/devtools exports. A page reload therefore
 * starts token-less; session continuity comes from Keycloak's httpOnly
 * SSO cookie via a one-shot silent signin (`useSilentBootstrap`) and
 * in-session renewal rides the silent iframe. Keycloak's
 * ssoSessionIdleTimeout remains the authoritative session control.
 *
 * Corollary the consumer owns: this posture is only as strong as the
 * XSS controls around it — serve your SPA with the asunset security
 * header set (CSP et al.; `asunset_core.http.SecurityHeadersMiddleware`
 * for FastAPI-served SPAs).
 */
export function createOidcConfig(opts: OidcConfigOptions): AsunsetOidcConfig {
  const redirectUri = opts.redirectUri ?? window.location.origin;
  const silentPath = opts.silentRenewPath ?? "/silent-renew.html";
  return {
    authority: `${opts.keycloakUrl}/realms/${opts.realm}`,
    client_id: opts.clientId,
    redirect_uri: redirectUri,
    post_logout_redirect_uri: opts.postLogoutRedirectUri ?? redirectUri,
    response_type: "code",
    scope: "openid profile email",
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    automaticSilentRenew: true,
    silent_redirect_uri: `${new URL(redirectUri).origin}${silentPath}`,
    // Clean the `?code=...&state=...` out of the URL after callback.
    onSigninCallback: () => {
      window.history.replaceState(
        {},
        document.title,
        window.location.pathname,
      );
    },
  };
}

import type { AuthProviderProps } from "react-oidc-context";
import { InMemoryWebStorage, WebStorageStateStore } from "oidc-client-ts";

const KEYCLOAK_URL = import.meta.env.VITE_KEYCLOAK_URL;
const KEYCLOAK_REALM = import.meta.env.VITE_KEYCLOAK_REALM;
const KEYCLOAK_CLIENT_ID = import.meta.env.VITE_KEYCLOAK_CLIENT_ID;

export const oidcConfig: AuthProviderProps = {
  authority: `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}`,
  client_id: KEYCLOAK_CLIENT_ID,
  redirect_uri: window.location.origin,
  post_logout_redirect_uri: window.location.origin,
  response_type: "code",
  scope: "openid profile email",
  // A7 token-storage posture: tokens live IN MEMORY ONLY — nothing in
  // localStorage/sessionStorage, so no token survives XSS-adjacent
  // storage reads or lands in backups/devtools exports. A page reload
  // therefore starts token-less; session continuity comes from
  // Keycloak's httpOnly SSO cookie via the silent-signin attempt in
  // App.tsx (prompt=none iframe). Keycloak's ssoSessionIdleTimeout
  // remains the authoritative session control.
  userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
  // In-session renewal: refresh token exists only in RAM; reload/new-tab
  // renewal rides the SSO cookie through the silent iframe below.
  automaticSilentRenew: true,
  silent_redirect_uri: `${window.location.origin}/silent-renew.html`,
  // Clean the `?code=...&state=...` out of the URL after callback.
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

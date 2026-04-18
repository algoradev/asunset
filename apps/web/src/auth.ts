import type { AuthProviderProps } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";

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
  // Persist tokens in localStorage so a reload doesn't kick the user out.
  // Acceptable for a solo-operator dev template; tighten to sessionStorage
  // or memory in deployments where XSS is a concern.
  userStore: new WebStorageStateStore({ store: window.localStorage }),
  // Silent refresh off by default — Keycloak's short access-token lifespan
  // + refresh tokens in localStorage is fine for this template.
  automaticSilentRenew: true,
  // Clean the `?code=...&state=...` out of the URL after callback.
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

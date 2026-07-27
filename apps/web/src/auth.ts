// The asunset auth posture comes from the SDK (Tier 1 kernel) — this
// file only feeds it the build-time env. Everything security-relevant
// (in-memory tokens, silent renew, PKCE wiring) lives in
// @asunset/web-sdk and is tested there.
import { createOidcConfig } from "@asunset/web-sdk";

export const oidcConfig = createOidcConfig({
  keycloakUrl: import.meta.env.VITE_KEYCLOAK_URL,
  realm: import.meta.env.VITE_KEYCLOAK_REALM,
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
});

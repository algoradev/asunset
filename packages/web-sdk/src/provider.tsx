import { useMemo } from "react";
import type { ReactNode } from "react";
import type { AuthProviderProps } from "react-oidc-context";
import { AuthProvider, useAuth } from "react-oidc-context";

import type { Fetcher } from "./fetch";

/**
 * The asunset auth provider — a named wrapper over react-oidc-context's
 * AuthProvider so consumers wire one thing by one name. Pass the result
 * of `createOidcConfig(...)`.
 */
export function AsunsetAuthProvider({
  config,
  children,
}: {
  config: AuthProviderProps;
  children: ReactNode;
}) {
  return <AuthProvider {...config}>{children}</AuthProvider>;
}

/**
 * The per-request credential carrier, stable per token. Replaces the
 * `const f = { accessToken: auth.user?.access_token }` idiom (a new
 * object identity every render) with a memoized one.
 */
export function useFetcher(): Fetcher {
  const auth = useAuth();
  const token = auth.user?.access_token;
  return useMemo(() => ({ accessToken: token }), [token]);
}

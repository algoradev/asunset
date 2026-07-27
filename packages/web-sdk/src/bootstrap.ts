import { useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";

/**
 * The one-shot silent-signin bootstrap that makes the in-memory token
 * posture livable: a reload starts token-less even when Keycloak's
 * httpOnly SSO cookie still holds a live session, so we try exactly ONE
 * silent signin (prompt=none iframe rides that cookie) before the
 * consumer shows its login screen.
 *
 *   "pending" — nothing attempted (or a live session exists)
 *   "trying"  — silent signin in flight; render your loading state
 *   "failed"  — genuinely logged out; render your login screen
 */
export type SilentBootstrapState = "pending" | "trying" | "failed";

export function useSilentBootstrap(): SilentBootstrapState {
  const auth = useAuth();
  const [silent, setSilent] = useState<SilentBootstrapState>("pending");

  useEffect(() => {
    if (auth.isLoading || auth.isAuthenticated || auth.activeNavigator) return;
    if (silent !== "pending") return;
    // A redirect callback in flight (?code=...) is handled by the
    // provider — don't race it with an iframe attempt.
    if (new URLSearchParams(window.location.search).has("code")) return;
    setSilent("trying");
    auth
      .signinSilent()
      .then((user) => setSilent(user ? "pending" : "failed"))
      .catch(() => setSilent("failed"));
  }, [auth, silent]);

  return silent;
}

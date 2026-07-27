// Runs inside the hidden silent-renew iframe. The consumer serves a
// tiny HTML page at the `silentRenewPath` given to createOidcConfig
// (default /silent-renew.html) whose only module script calls this.
// signinSilentCallback() posts the authorization response back to the
// parent frame's UserManager; settings are irrelevant here because the
// callback only relays the response URL.
import { UserManager } from "oidc-client-ts";

export function runSilentRenewCallback(): void {
  new UserManager({ authority: "", client_id: "", redirect_uri: "" })
    .signinSilentCallback()
    .catch((err: unknown) => {
      // Surfaced by the parent as a failed silent signin — log for devtools.
      console.error("silent-renew callback failed", err);
    });
}

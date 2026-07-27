import { describe, expect, it } from "vitest";
import { InMemoryWebStorage, WebStorageStateStore } from "oidc-client-ts";

import { createOidcConfig } from "../src/config";

const base = {
  keycloakUrl: "https://auth.example.test",
  realm: "asunset",
  clientId: "asunset-web",
};

describe("createOidcConfig", () => {
  it("composes the authority from url + realm", () => {
    const c = createOidcConfig(base);
    expect(c.authority).toBe("https://auth.example.test/realms/asunset");
    expect(c.client_id).toBe("asunset-web");
    expect(c.response_type).toBe("code");
    expect(c.scope).toBe("openid profile email");
  });

  it("A7: tokens live in memory only", () => {
    const c = createOidcConfig(base);
    expect(c.userStore).toBeInstanceOf(WebStorageStateStore);
    // Reach into the store to assert the backing storage class — this IS
    // the contract, not an implementation detail.
    const store = (c.userStore as WebStorageStateStore & { _store: unknown })[
      "_store"
    ];
    expect(store).toBeInstanceOf(InMemoryWebStorage);
  });

  it("defaults redirect URIs to window origin and silent renew to /silent-renew.html", () => {
    const c = createOidcConfig(base);
    expect(c.redirect_uri).toBe(window.location.origin);
    expect(c.post_logout_redirect_uri).toBe(window.location.origin);
    expect(c.automaticSilentRenew).toBe(true);
    expect(c.silent_redirect_uri).toBe(
      `${window.location.origin}/silent-renew.html`,
    );
  });

  it("honors explicit redirect + silent-renew path", () => {
    const c = createOidcConfig({
      ...base,
      redirectUri: "https://app.example.test/shell",
      silentRenewPath: "/static/renew.html",
    });
    expect(c.redirect_uri).toBe("https://app.example.test/shell");
    // silent renew is origin-anchored, not path-anchored
    expect(c.silent_redirect_uri).toBe(
      "https://app.example.test/static/renew.html",
    );
  });

  it("onSigninCallback strips the auth-code query from the URL", () => {
    window.history.replaceState({}, "", "/notes?code=abc&state=xyz");
    const c = createOidcConfig(base);
    c.onSigninCallback?.(undefined as never);
    expect(window.location.search).toBe("");
    expect(window.location.pathname).toBe("/notes");
  });
});

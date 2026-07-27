# @asunset/web-sdk — the browser auth kernel (Tier 1)

The one implementation of asunset's browser auth posture (A7): OIDC
auth-code + PKCE, **in-memory tokens** (nothing auth-bearing ever
touches localStorage/sessionStorage), silent renew through Keycloak's
httpOnly SSO cookie, HIPAA idle logoff, and a fetch core that stamps
`Authorization` + `X-Correlation-Id` on every request.

Headless by contract: no components, no i18n, no styling. You render
every pixel; the kernel owns the token lifecycle. The inverse also
binds: **if your UI does auth against asunset identity, it does it
through this package** — hand-rolled OIDC/token handling is a
review-blocker ([`docs/frontend-sdk-decision.md`](../../docs/frontend-sdk-decision.md)).

## Install (Option S — source alias)

The SDK ships as TypeScript source from your vendored subtree. No
registry, no build artifacts; the subtree pin is the version.

1. Alias it in `vite.config.ts` **and** `tsconfig.json`:

```ts
// vite.config.ts
resolve: {
  alias: {
    "@asunset/web-sdk": path.resolve(
      __dirname, "path/to/vendor/asunset/packages/web-sdk/src/index.ts"),
  },
},
```

```jsonc
// tsconfig.json → compilerOptions.paths
"@asunset/web-sdk": ["path/to/vendor/asunset/packages/web-sdk/src/index.ts"]
```

2. Declare the runtime deps yourself (they're peers, not bundled):

```sh
npm install react-oidc-context oidc-client-ts   # react ^18 || ^19
```

The alias path is a contract surface — it moves only with a documented
breaking change.

## Wire it (five steps)

```tsx
// 1. Config — explicit values in, no hidden env reads.
import { createOidcConfig } from "@asunset/web-sdk";
export const oidcConfig = createOidcConfig({
  keycloakUrl: "https://your-host",      // public URL, /auth-suffixed in path-routed modes
  realm: "asunset",
  clientId: "asunset-web",
});

// 2. Provider — once, at the root.
import { AsunsetAuthProvider } from "@asunset/web-sdk";
<AsunsetAuthProvider config={oidcConfig}>
  <App />
</AsunsetAuthProvider>;

// 3. Login gate — YOUR screen, the SDK's state machine.
import { useAuth, useSilentBootstrap } from "@asunset/web-sdk";
function Gate() {
  const auth = useAuth();
  const silent = useSilentBootstrap();  // one silent try rides the SSO cookie
  if (auth.isLoading || silent === "trying") return <YourSpinner />;
  if (!auth.isAuthenticated)
    return <YourLoginScreen onSignIn={() => auth.signinRedirect()} />;
  return <YourApp />;
}

// 4. Requests — bearer + correlation on everything.
import { createApiCore, useFetcher } from "@asunset/web-sdk";
const core = createApiCore("");           // "" = same-origin
const f = useFetcher();                    // memoized { accessToken }
await core.request("/api/things", { method: "GET" }, f);
// Foreign clients with their own transport: authHeaders(f) returns the
// header record (the `headers?: () => Record` seam shape).

// 5. Idle logoff — the hook is headless; render your own warning dialog.
import { useIdleLogout } from "@asunset/web-sdk";
const idle = useIdleLogout({ onLogout: () => auth.signoutRedirect(), enabled: true });
// idle.warning / idle.secondsLeft / idle.reset drive your dialog.
```

## The silent-renew page (required)

In-memory tokens mean a reload starts token-less; continuity comes from
a hidden iframe riding the SSO cookie. Serve a page at
`/silent-renew.html` on your SPA origin (or pass `silentRenewPath`):

```html
<!doctype html>
<html><head><meta charset="UTF-8" /></head>
<body><script type="module" src="/src/silent-renew.ts"></script></body></html>
```

```ts
// src/silent-renew.ts
import { runSilentRenewCallback } from "@asunset/web-sdk";
runSilentRenewCallback();
```

Vite: add the html as a second rollup input so it lands in `dist/`.

## The CSP corollary (not optional)

In-memory tokens are only as strong as the XSS posture around them. If
your SPA is served by FastAPI, add
`asunset_core.middleware.SecurityHeadersMiddleware` **in the same slice
you wire this kit**; opting out requires `disabled_reason=` and is
logged loudly. (nginx-served SPAs: mirror
`apps/web/nginx.conf.template`.)

## What this is not

- Not backend security: an API that doesn't validate tokens is not
  secured by the browser sending them. "SDK wired" and "enforcement
  wired" are separate acceptance states — never report the first as the
  second.
- Not a data layer: typed platform client + hooks are Tier 2 (separate,
  à la carte).
- Not a component library: `@asunset/react` remains a reserved name
  with its own trigger.

## Tests

`npm test` (vitest, jsdom): config posture, fetch-core header/error
semantics, idle-logoff timing (including the warning-window
no-reset rule), silent-bootstrap state machine. The reference app
`apps/web/` consumes this package — its build is the compile-level
integration test, and `tools/deploy/a7_hardening_test.go` pins that it
keeps consuming rather than re-growing local auth.

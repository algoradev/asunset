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

## Tier 2a — the typed platform client

Framework-free platform data access over the same core — orgs, members,
invites (including the exactly-once `temporary_password` contract),
teams, audit, `me`/`meFeatures`, bootstrap, reconcile. Safe from any
state layer: raw `useState`/`useEffect`, TanStack, anything.

```ts
import { createApiCore, createPlatformClient, useFetcher } from "@asunset/web-sdk";

const core = createApiCore("");                 // "" = same-origin
const platform = createPlatformClient(core);

const f = useFetcher();
const me = await platform.me(f);                // Me
const members = await platform.listOrgMembers(f); // OrgMember[]
const events = await platform.listAuditEvents(f, { event_type: "note.created" });
```

All platform types (`Me`, `OrgMember`, `InviteResult`, `AuditEvent`, …)
are exported. Your product's own resources stay in your own client —
this surface is platform-only, and it grows via subtree pull, not via
your fork.

**Error handling**: non-2xx throws `ApiError` with `status`, a clean
`message`, the server-echoed `correlationId`, and — when the API
provides one — a stable `code`. Branch UI on `code`, never by matching
message strings (messages are copy, codes are contract):

```ts
catch (e) {
  if (e instanceof ApiError && e.code === "already_a_member") { ... }
}
```

## Tier 2b — headless hooks (opt-in, TanStack)

If your app runs `@tanstack/react-query` (^5), the hooks layer owns
what's expensive to get wrong — query keys, cache invalidation, the
composite flows (email→lookup→add; resend carrying the recipient email
through), token-gated enabling — and nothing about presentation.
Separate entry so 2a-only consumers never resolve TanStack:

```ts
// alias BOTH paths — the /hooks entry FIRST (alias matching is prefix-based):
//   "@asunset/web-sdk/hooks" → vendor/asunset/packages/web-sdk/src/hooks.ts
//   "@asunset/web-sdk"       → vendor/asunset/packages/web-sdk/src/index.ts
import { createPlatformHooks, platformKeys } from "@asunset/web-sdk/hooks";

export const { useMe, useOrgMembers, useTeams, useInviteMember, ... } =
  createPlatformHooks(platform);

// pages keep only their own UI reactions:
const inviteM = useInviteMember({
  onSuccess: (result) => {/* your toast, your dialog state */},
  onError: (e) => {/* branch on e.code, render your copy */},
});
inviteM.mutate({ email, role });
```

Invalidations run in the hook regardless of your callbacks; invalidate
custom cache entries through `platformKeys`, never hand-typed strings.
`useFeatureSet<YourFeatureKey>()` gives compile-checked feature gating
over your generated key union. The reference app's org/teams/audit
pages consume exactly these hooks — read them as the worked example.

## Local dev against the smoke stack (copy-paste)

A foreign Vite app on `localhost:5173` talking to a local asunset stack
(compose project from this repo, defaults):

```ts
// OIDC — the dev realm's values:
const oidcConfig = createOidcConfig({
  keycloakUrl: "http://localhost:8080",
  realm: "asunset",
  clientId: "asunset-web",   // dev client already allows localhost:5173 origins
});
```

```ts
// vite.config.ts — createApiCore("") means same-origin, so proxy the
// FULL platform surface to the api container (not just the two paths
// you call first; the client also uses /teams, /users, /audit):
server: {
  proxy: Object.fromEntries(
    ["/platform", "/orgs", "/teams", "/users", "/audit"].map((p) => [
      p, { target: "http://localhost:8000", changeOrigin: true },
    ]),
  ),
},
build: {
  rollupOptions: {
    input: { main: "index.html", "silent-renew": "silent-renew.html" },
  },
},
```

Dev-realm caveat: seeded users can carry `requiredActions` (e.g.
`CONFIGURE_TOTP`) that block sign-in with "Account is not fully set up"
— the recovery dance is documented in
[`docs/runbooks/operator-token.md`](../../docs/runbooks/operator-token.md).

A complete working fixture lives at
[`examples/foreign-ui-min/`](../../examples/foreign-ui-min/) — the
permanent foreign-consumer compile fixture, built docs-only by caliper
(exercise 4).

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
- Not a hooks layer (yet): the headless TanStack hooks are Tier 2b,
  separate and opt-in — the 2a client above never imports a state
  library.
- Not a component library: `@asunset/react` remains a reserved name
  with its own trigger.

## Tests

`npm test` (vitest, jsdom): config posture, fetch-core header/error
semantics, idle-logoff timing (including the warning-window
no-reset rule), silent-bootstrap state machine. The reference app
`apps/web/` consumes this package — its build is the compile-level
integration test, and `tools/deploy/a7_hardening_test.go` pins that it
keeps consuming rather than re-growing local auth.

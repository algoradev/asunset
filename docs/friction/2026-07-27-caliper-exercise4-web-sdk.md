# Caliper Exercise 4: foreign UI consuming @asunset/web-sdk

Agent: caliper  
Branch: `caliper/exercise4-foreign-ui-web-sdk`  
Date: 2026-07-27  
Target: `examples/foreign-ui-min`

## Outcome

Built the smallest standalone Vite + React foreign UI fixture I could justify:

- Consumes `@asunset/web-sdk` by source alias to `../../packages/web-sdk/src/index.ts`.
- Declares the SDK peer runtime dependencies in the consumer package.
- Wires Tier 1: `AsunsetAuthProvider`, `useSilentBootstrap`, a consumer-owned
  login screen, `silent-renew.html`, `runSilentRenewCallback`, `useIdleLogout`,
  and `useFetcher`.
- Wires Tier 2a: `createApiCore("")`, `createPlatformClient(core)`,
  `platform.me(fetcher)`, and `platform.listOrgMembers(fetcher)`.
- Uses Vite proxy rules so the fixture makes same-origin browser requests to
  `/platform` and `/orgs`, then forwards them to the live smoke API.

I did not reuse or inspect `apps/web` source. I did inspect
`packages/web-sdk/package.json` as package metadata to confirm the peer deps
that the README already named.

## Timeline

- 10 min: read allowed docs: `packages/web-sdk/README.md`,
  `docs/consuming-asunset.md`, linked `docs/frontend-sdk-decision.md`, and the
  linked identity-contract sections on token storage/idle logout.
- 5 min: checked live Keycloak client metadata for the allowed redirect origins.
  The `asunset-web` client allows both `http://localhost:3000/*` and
  `http://localhost:5173/*`.
- 25 min: created `examples/foreign-ui-min` with Vite, React, source alias,
  silent-renew page, login gate, idle warning UI, fetcher, and Tier-2a platform
  calls.
- 5 min: installed dependencies and fixed package dependency split so Vite
  tooling stays in `devDependencies`.
- 20 min: verified build and live browser behavior. Most of this was Playwright
  runner setup, not app work.
- 10 min: recorded findings and wrote this report.

## What Worked

The SDK README was enough to wire the real app without opening SDK source. The
five-step flow maps directly to code: config, provider, login gate, fetcher,
idle logout. Tier 2a also worked exactly as documented: `me()` and
`listOrgMembers()` compiled and returned the live smoke data.

Option S was precise enough for both Vite and TypeScript aliasing. The
silent-renew page requirement also gave the exact file shape and reminded me to
add it as a second Rollup input.

## Frictions

1. **Foreign dev same-origin was underspecified.**  
   The README recommends `createApiCore("")` for same-origin requests, but a
   Vite foreign UI on `localhost:5173` is not same-origin with the smoke API on
   `localhost:8000` unless the consumer adds a dev proxy. I guessed the Vite
   proxy mapping for `/platform` and `/orgs`. This should be a short
   copy-paste block in the foreign-UI docs.

2. **Local smoke values were not on one screen.**  
   The docs show `keycloakUrl: "https://your-host"` and `clientId:
   "asunset-web"`, but the exercise required the live local stack. I had to
   infer `keycloakUrl: "http://localhost:8080"` and verify the `asunset-web`
   redirect origins through Keycloak admin metadata. A "localhost smoke config"
   snippet would remove that branch.

3. **Alice's dev credentials were not actually ready after init.**  
   The direct grant check failed with:

   ```json
   {
     "error": "invalid_grant",
     "error_description": "Account is not fully set up"
   }
   ```

   Keycloak showed:

   ```json
   {
     "id": "d253ea87-1650-49f7-889c-d0cec38a546f",
     "username": "alice",
     "requiredActions": ["CONFIGURE_TOTP"]
   }
   ```

   I cleared the required action through dev-only Keycloak admin recovery to
   complete browser verification. This is the same local-loop friction from
   earlier exercises and is now the biggest practical obstacle to repeatable
   foreign-UI smoke verification.

4. **Browser verification tooling was not documented.**  
   The exercise asked for devtools checks. I used a temporary Playwright runner,
   but `npx playwright` did not expose imports for a raw `/tmp` script, and the
   freshly installed runner did not have a matching browser cache. I ended up
   using `/snap/bin/chromium`. This is not an SDK problem, but if this example
   becomes the permanent second compile fixture, a small scripted verification
   target would prevent every tester from reinventing this.

5. **One linked identity doc still has stale wording.**  
   `docs/identity-contract.md` section 6.1 correctly says in-memory storage is
   shipped and local/session storage are not used. Later, line 338 still says:
   "Revisit `localStorage` token storage for regulated deployments." That stale
   sentence conflicts with the 2026-07-27 amendment and should be removed or
   rewritten.

## Verdicts By Doc Section

| Source | Verdict |
|---|---|
| `packages/web-sdk/README.md` install section | Pass. Source alias and peer dependency model were clear enough. |
| `packages/web-sdk/README.md` five-step wiring | Pass. I could implement provider, login gate, fetcher, and idle hook from the snippets. |
| `packages/web-sdk/README.md` silent-renew page | Pass. Exact files were clear; Rollup second-input note was necessary and correct. |
| `packages/web-sdk/README.md` Tier 2a client | Pass. `createPlatformClient`, `me`, and `listOrgMembers` worked without source-reading. |
| `docs/consuming-asunset.md` foreign-UI path | Partial. Good doctrine and ingress context, but missing the minimal local Vite dev shape. |
| `docs/frontend-sdk-decision.md` | Pass for governance. It explains why the auth kernel is mandatory, but it is not a wiring doc. |
| `docs/identity-contract.md` | Partial. The amended storage posture is clear in section 6.1; the later localStorage sentence is stale. |

## Questions I Could Not Ask

- Should the permanent fixture run on `5173` with Vite proxy, or should it
  deliberately take over `3000` and replace the demo web during verification?
- Should `@vitejs/plugin-react`, `vite`, and TypeScript be part of this fixture's
  committed dev deps, or should the repo eventually manage examples through a
  shared JS workspace?
- Should the example include a committed browser smoke test, or is compile-only
  enough for the "second compile fixture" guard?
- Is the foreign UI expected to own CSP only in production serving, or should a
  dev fixture demonstrate headers somehow?
- Should `createApiCore("")` docs explicitly recommend a Vite proxy for
  localhost foreign UI development?

## Verification

Build:

```text
npm run build
tsc --noEmit && vite build
dist/silent-renew.html
dist/index.html
```

Live browser verification against `asunset-smoke`:

```text
http://localhost:5173/ -> login via Keycloak -> back to app
rendered Alice Admin and org member list
reload stayed authenticated
localStorage before reload: []
sessionStorage before reload: []
localStorage after reload: []
sessionStorage after reload: []
```

Captured browser requests:

```json
[
  {
    "url": "http://localhost:5173/platform/me",
    "authorization": "present",
    "correlation": "06bb742d3437e596cbf817a7"
  },
  {
    "url": "http://localhost:5173/orgs/current/members",
    "authorization": "present",
    "correlation": "c078218b53a6a137827a945e"
  },
  {
    "url": "http://localhost:5173/platform/me",
    "authorization": "present",
    "correlation": "f4b935ef8796aff2e4bf0345"
  },
  {
    "url": "http://localhost:5173/orgs/current/members",
    "authorization": "present",
    "correlation": "254784498d3936ba2373a6d9"
  }
]
```

The duplicate request pair is expected: one pair after login and one pair after
reload.

## Verdict

PASS with local-dev friction. A zero-context foreign UI consumer can wire Tier 1
and Tier 2a from the SDK README without reading SDK source. The single biggest
improvement is a copy-paste "foreign Vite against smoke stack" section:
localhost OIDC config, Vite same-origin proxy, silent-renew Rollup input, and
the Alice required-action recovery caveat.

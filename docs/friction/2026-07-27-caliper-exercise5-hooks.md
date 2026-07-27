# Caliper Exercise 5: Tier 2b hooks consumption

Agent: caliper  
Branch: `caliper/exercise5-web-sdk-hooks`  
Date: 2026-07-27  
Target: `examples/foreign-ui-min`

## Outcome

Extended the permanent foreign UI fixture to consume `@asunset/web-sdk/hooks`:

- Added `@tanstack/react-query`.
- Wired `QueryClientProvider`.
- Added the documented source aliases for both `@asunset/web-sdk/hooks` and
  `@asunset/web-sdk`, with the hooks alias first.
- Replaced the manual `useState`/`useEffect` Tier 2a data loading with
  `useMe`, `useOrgMembers`, and `useTeams`.
- Added a create/delete team flow through `useCreateTeam` and `useDeleteTeam`.
- Added an invite-Alice error probe through `useInviteMember`, branching on
  `err instanceof ApiError && err.code === "already_a_member"` and rendering the
  code in the UI.

I did not open SDK source or `apps/web` source. I read the updated SDK README,
the consuming guide section it points to, and package/build metadata for the
fixture.

## Timeline

- 10 min: confirmed `main` was at `02dcddd`, branched fresh, read the updated
  SDK README and consuming guide hook/error sections.
- 10 min: installed `@tanstack/react-query`, added the `/hooks` alias before the
  root alias in both Vite and TypeScript config, and expanded the dev proxy to
  the documented platform path list.
- 25 min: converted the fixture UI to hooks and added team create/delete plus
  duplicate-invite error rendering.
- 5 min: first build caught one undocumented mutation argument shape:
  `useDeleteTeam().mutate(...)` expects `{ teamId: string }`, not a raw string.
- 45 min: live verification. The first duplicate-invite probe hit the old
  string-error API shape because the running smoke API was stale; rebuilding the
  API made the structured `already_a_member` code appear. The rebuild also
  re-added Alice's `CONFIGURE_TOTP` required action, so I cleared it again via
  dev-only Keycloak admin recovery.
- 10 min: wrote this report and checked cleanup.

## What Worked

The Tier 2b README section made the core integration clear: install TanStack,
alias the `/hooks` subpath first, create hooks from the 2a platform client, and
keep UI callbacks presentation-only. The alias-order warning was prominent
enough that I did not trip over prefix matching.

The hook names for the requested reads and mutations were discoverable by
reasonable convention and compile feedback: `useMe`, `useOrgMembers`,
`useTeams`, `useCreateTeam`, `useDeleteTeam`, and `useInviteMember`.

The invalidation behavior held live. The browser run captured `POST /teams`
followed by an automatic `GET /teams`, then `DELETE /teams/{id}` followed by
another automatic `GET /teams`. The fixture code never calls `refetch()`.

## Frictions

1. **Mutation payload shapes are not documented.**  
   The README shows `useInviteMember({ ... }).mutate({ email, role })`, but not
   create/delete team argument shapes. I guessed `deleteTeam.mutate(team.id)`;
   TypeScript corrected it:

   ```text
   src/main.tsx(161,52): error TS2345: Argument of type 'string' is not assignable to parameter of type '{ teamId: string; }'.
   ```

   The fix was `deleteTeam.mutate({ teamId: team.id })`.

2. **Structured errors required a stale live API rebuild that the exercise did
   not mention.**  
   Before rebuilding, duplicate invite returned old string detail:

   ```json
   {"detail":"already a member with a different role - use PATCH to change role"}
   ```

   After `docker compose -p asunset-smoke --env-file .env -f compose.yml up -d
   --build api`, the same request returned the documented structured shape:

   ```json
   {
     "detail": {
       "code": "already_a_member",
       "message": "already a member with a different role - use PATCH to change role"
     }
   }
   ```

3. **The dev-realm TOTP ping-pong still recurs on API rebuilds.**  
   Rebuilding the API reran `keycloak-init`, which put Alice back into:

   ```json
   {"requiredActions":["CONFIGURE_TOTP"]}
   ```

   Password login then failed with:

   ```json
   {
     "error": "invalid_grant",
     "error_description": "Account is not fully set up"
   }
   ```

   I cleared the required action through dev-only Keycloak admin recovery before
   running the browser verification.

4. **README has one stale post-Tier-2b bullet.**  
   The same README now documents Tier 2b, but the "What this is not" section
   still says:

   ```text
   Not a hooks layer (yet): the headless TanStack hooks are Tier 2b,
   separate and opt-in
   ```

   The second clause is still useful; the "not a hooks layer (yet)" lead-in is
   no longer true.

5. **`platformKeys` is mentioned but not needed in the minimal path.**  
   The docs say to invalidate custom cache entries through `platformKeys`, but
   the exercise only needed built-in hook invalidations. I did not use
   `platformKeys`, which is fine for this fixture, but a one-line example of
   `queryClient.invalidateQueries({ queryKey: platformKeys.teams() })` would
   make the registry's shape more concrete.

## Verdicts By Doc Section

| Source | Verdict |
|---|---|
| SDK README Tier 2b hooks | Pass. The integration shape and alias ordering were clear. |
| SDK README mutation example | Partial. Invite mutation shape is shown; team create/delete shapes are not. |
| SDK README error handling | Pass after API rebuild. The `ApiError.code === "already_a_member"` branch worked exactly as stated. |
| SDK README local smoke section | Pass. The full proxy list and localhost OIDC values are now on one screen. |
| SDK README "What this is not" | Fail. It still says the SDK is not a hooks layer yet. |
| Consuming guide API error contract | Pass. It clearly says branch on `ApiError.code`, not message strings. |

## Questions I Could Not Ask

- Should the fixture demonstrate `platformKeys` directly, or is proving built-in
  hook invalidation enough?
- Should the permanent compile fixture include a committed browser smoke script
  for the create/delete/error path, or should that remain external?
- Should the README list every hook returned by `createPlatformHooks`, including
  mutation variable shapes?
- Should local smoke exercises always rebuild API after a new main shipment, or
  should doctor expose "running API image is older than repo main"?
- Should `keycloak-init` avoid re-adding `CONFIGURE_TOTP` in the dev smoke loop
  once a test agent clears it?

## Verification

Build:

```text
npm run build
tsc --noEmit && vite build
```

Live browser verification against `asunset-smoke`:

```text
login via Keycloak -> back to http://localhost:5173/
rendered Alice Admin, org members, and Teams
reload stayed authenticated
localStorage before reload: []
sessionStorage before reload: []
localStorage after reload: []
sessionStorage after reload: []
created team: caliper-hooks-1785181916809
deleted team: caliper-hooks-1785181916809
duplicate invite rendered: Invite code: already_a_member
cleanup check: no teams with prefix caliper-hooks-
```

Captured request sequence:

```json
[
  {"method":"GET","url":"http://localhost:5173/platform/me","authorization":"present","correlation":"e720740c0b5f7a27cdc8bc9d"},
  {"method":"GET","url":"http://localhost:5173/orgs/current/members","authorization":"present","correlation":"16db2215c58a820231587130"},
  {"method":"GET","url":"http://localhost:5173/teams","authorization":"present","correlation":"34257517e3a3a5149b26c70b"},
  {"method":"POST","url":"http://localhost:5173/teams","authorization":"present","correlation":"a02d0a25464ca782a6f8c37c"},
  {"method":"GET","url":"http://localhost:5173/teams","authorization":"present","correlation":"1fe58ea70f27093a2e0bd3de"},
  {"method":"DELETE","url":"http://localhost:5173/teams/b9564e0d-88e2-49a6-a5af-8390714669cd","authorization":"present","correlation":"c83a4ceb70cda9e8c5c72209"},
  {"method":"GET","url":"http://localhost:5173/teams","authorization":"present","correlation":"c1d7c8a39081e4386aadab14"},
  {"method":"POST","url":"http://localhost:5173/orgs/current/invites","authorization":"present","correlation":"6a9ab9e8ee96a9188923e0c6"}
]
```

## Verdict

PASS with small docs gaps and live-stack friction. A zero-context foreign UI
consumer can adopt Tier 2b without opening SDK source. The biggest improvement:
add a returned-hooks reference table to the README, including mutation variable
shapes and what each mutation invalidates.

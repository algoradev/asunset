# Decision record — foreign UIs and the frontend SDK ("B + SDK")

**Ruled by:** Avi, 2026-07-27 · **Proposal:** report 93 (dbt-test `reports/93-asunset-frontend-sdk-proposal.md`) · **Reviews:** kestrel (ops), atlas (OpsRoom composition), relay (architecture), juniper (doctrine) — all four ratified with guards, thread `022abab1352c`. Resolves report 92 §1 (Gap 1).

This document is the canonical record of the ruling. The consumer-facing
mechanics live in [`consuming-asunset.md`](consuming-asunset.md); tier
details and audit evidence live in report 93.

## The ruling

**B on ingress and UI ownership; A on the auth kernel — delivered as a
tiered SDK.** Consumers may ship a fully independent frontend. What they
may never do is reimplement asunset's browser auth.

| Tier | What | Contract status |
|---|---|---|
| 1 | `@asunset/web-sdk` — the auth kernel: OIDC/PKCE config factory, in-memory token store, silent renew, idle logout, correlation+bearer fetch core, auth provider + fetcher context | **Mandatory** for any foreign UI doing auth |
| 2a | Typed platform client (framework-free) | À la carte |
| 2b | Headless TanStack Query hooks | À la carte, opt-in (TanStack is a peer dep of 2b only — never of 1 or 2a) |
| 3 | `apps/web` | **Reference implementation** — fork path unchanged and fully supported; rewritten to consume tiers 1+2 (dogfood = no second implementation) |
| — | Foreign-UI ingress recipe (consumer-owned Caddyfile via the sanctioned override-mount seam) | Supported contract surface — see consuming-asunset.md |

## Ratified rules (doctrine, juniper)

1. **One browser-auth implementation.** The rule forces *singularity
   wherever browser auth exists*, not auth everywhere: an unauthenticated
   dev/standalone surface is compliant; the moment a browser surface does
   auth against asunset identity, only the SDK path is reviewable.
   Hand-rolled OIDC/token lifecycle is a **review-blocker**, same class as
   hand-rolled FGA clients. The rule binds **all** consumers of asunset
   identity regardless of distribution mechanism; "cannot consume the SDK"
   (non-JS frontend, incompatible stack) is a platform conversation raised
   *before* building, never an exemption.
2. **Reach-blind tiers.** The SDK ships no pixels; consumers ship no token
   lifecycle. Neither side may ever need to know the other's domain to be
   correct.
3. **Tier-3 relabel is a truth correction.** The shell always was the
   reference implementation; the label catches up. Dogfooding makes it
   enforceable.
4. **Convention → structure.** The old fork rule "keep `auth.ts`/`api.ts`
   byte-identical" becomes "import them": the same invariant, but
   divergence is now inexpressible rather than merely forbidden.
5. **CSP is part of Tier 1's security boundary.** In-memory tokens without
   an XSS posture are decorative. The `SecurityHeadersMiddleware`
   (asunset_core) is **opt-out-with-recorded-reason**, not silently
   optional, and the posture is doctor-checkable per instance. A foreign
   UI wiring the auth kernel takes the header posture *in the same slice*.
6. **Acceptance split.** "SDK wired" (browser holds tokens, sends headers)
   and "backend enforcement wired" (API validates and enforces the
   principal chain) are separate acceptance states. Nothing — doctor,
   readiness, UI, docs, status boards — may report a consumer as *secured*
   on SDK presence alone.

## Distribution (ruled: Option S for v1)

Source-alias: the SDK lives as TypeScript source under
`packages/web-sdk/`; consumers alias `@asunset/web-sdk` to
`vendor/asunset/packages/web-sdk/src` and declare its runtime deps
themselves. The subtree pin is the version axis — a security fix in the
kernel propagates through one named mechanism, and the consumed kernel
version is reportable (doctor surfaces the pin). Guards (relay): the
package is strict-clean, imports only declared deps, never imports from
`apps/web`, reads env only through explicit factories; the alias path is
itself a contract surface (moving it is a breaking change); CI compiles
the SDK from both the reference app and a foreign-consumer shape.
**Named trigger for Option P** (packed artifact / registry): a
non-subtree consumer appears, or SDK/platform version skew becomes
painful.

## Deferred with named triggers

- **SSE auth**: fetch-streaming is the end-state; a short-TTL single-use
  ticket (never the bearer) is the only acceptable interim; cookie-scoped
  stream auth is rejected (A7 closed that surface). Lands with the
  consumer's stream-auth slice, not with SDK v1.
- **`@asunset/react`** (component tier): name stays reserved; original
  trigger unchanged (second-UI shell-drift pain or post-adoption ask).
- **Structured error codes as a platform API rule** ("codes, never
  message-string matching"): enters the consuming guide when the SDK's
  error-code work lands with its first real implementation.

## Sequencing

Lane 1 (ingress recipe) unparks K2 and owes nothing to the SDK. Tier 1
lands next and can be wired by consumers immediately — but per rule 6 it
is not "security" until the consumer's backend enforcement slice (S1 for
OpsRoom) is live. Done-ness of the SDK build is externally verified:
caliper exercise 4 consumes it docs-only in a fresh context.

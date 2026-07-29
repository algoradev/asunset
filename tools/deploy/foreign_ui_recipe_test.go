package main

// The foreign-UI ingress recipe (consuming-asunset.md §5b, ruled in
// docs/frontend-sdk-decision.md) is a contract surface: consumers build
// their Caddyfile and overlay against its exact instructions. These
// tests pin the load-bearing strings so a docs edit can't silently
// break the recipe, and pin the doctor check the recipe points at.
//
// The two compose behaviors the recipe relies on were verified against
// docker compose v2 (2026-07-27): duplicate volume targets dedupe with
// the later file winning, and `depends_on: !override` composes cleanly
// with `web`/`api` profiled out — without it compose refuses with
// `service "caddy" depends on undefined service "web"`.

import (
	"strings"
	"testing"
)

func TestForeignUIRecipeCarriesTheNonNegotiables(t *testing.T) {
	guide := readRepoFile(t, "docs/consuming-asunset.md")

	// The verbatim /auth block — the platform-wide login dependency.
	if !strings.Contains(guide, "handle /auth/* {") ||
		!strings.Contains(guide, "reverse_proxy keycloak:8080") {
		t.Error("consuming guide lost the verbatim /auth Caddy block")
	}
	// The depends_on reset and its failure mode, named.
	if !strings.Contains(guide, "depends_on: !override") {
		t.Error("consuming guide lost the depends_on !override instruction")
	}
	if !strings.Contains(guide, `depends on undefined service "web"`) {
		t.Error("consuming guide lost the F1 failure-mode string (the 'why' of the reset)")
	}
	// The override-mount seam with the project-dir climb-out.
	if !strings.Contains(guide, "../../deploy/Caddyfile:/etc/caddy/Caddyfile:ro") {
		t.Error("consuming guide lost the override-mount example with the ../../ climb-out")
	}
	// Preserve-vs-strip must be an explicit declaration, not a footnote.
	if !strings.Contains(guide, "handle_path /api/*") || !strings.Contains(guide, "handle /api/*") {
		t.Error("consuming guide must show BOTH strip (handle_path) and preserve (handle) forms")
	}
	// The auth-kernel mandate travels with the recipe.
	if !strings.Contains(guide, "@asunset/web-sdk") ||
		!strings.Contains(guide, "review-blocker") {
		t.Error("foreign-UI section lost the mandatory auth-kernel rule")
	}
}

func TestFrontendSDKDecisionRecordExists(t *testing.T) {
	rec := readRepoFile(t, "docs/frontend-sdk-decision.md")
	for _, must := range []string{
		"B on ingress and UI ownership; A on the auth kernel",
		"review-blocker",
		"Option S",
		"reportable",                 // kernel version reportability (juniper)
		"opt-out-with-recorded-reason", // CSP middleware posture
		"SDK presence alone",         // acceptance split
	} {
		if !strings.Contains(rec, must) {
			t.Errorf("decision record lost ratified language: %q", must)
		}
	}
}

func TestForeignConsumerFixtureExists(t *testing.T) {
	// examples/foreign-ui-min is the permanent second compile shape for
	// the SDK (relay's Option-S guard: reference app + one foreign
	// consumer). Built docs-only by caliper (exercise 4); it must keep
	// consuming via the documented alias, never by reaching into apps/web.
	viteCfg := readRepoFile(t, "examples/foreign-ui-min/vite.config.ts")
	if !strings.Contains(viteCfg, "@asunset/web-sdk") {
		t.Error("foreign-ui-min must alias @asunset/web-sdk (Option S)")
	}
	appSrc := readRepoFile(t, "examples/foreign-ui-min/src/main.tsx")
	// Since exercise 5 the fixture consumes the Tier-2b hooks (which
	// carry the fetcher internally) — the pin follows the contract, not
	// a particular import list.
	for _, must := range []string{
		"AsunsetAuthProvider", "useSilentBootstrap", "useIdleLogout",
		"createPlatformClient", "createPlatformHooks",
	} {
		if !strings.Contains(appSrc, must) {
			t.Errorf("foreign-ui-min lost its %s wiring — the fixture no longer proves the contract", must)
		}
	}
	if strings.Contains(appSrc, "apps/web") {
		t.Error("foreign-ui-min must not reach into apps/web")
	}
}

func TestDoctorProbesTheFrontDoorAuthRoute(t *testing.T) {
	doctor := readRepoFile(t, "tools/deploy/doctor.go")
	if !strings.Contains(doctor, `"edge-auth-route"`) {
		t.Error("doctor lost the edge-auth-route check the recipe points consumers at")
	}
	guide := readRepoFile(t, "docs/consuming-asunset.md")
	if !strings.Contains(guide, "edge-auth-route") {
		t.Error("consuming guide no longer names the doctor check for the recipe")
	}
}

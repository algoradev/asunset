package main

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// Regression guard for the wirebit-crm-client tailnet bootstrap bug: a fresh
// tailscale init left the asunset-web Keycloak client on the realm-export
// localhost dev URIs (http://localhost:5173), so Keycloak rejected login with
// "Invalid parameter: redirect_uri". The fix derives the host from
// TAILSCALE_HOST in keycloak-init and fails loud rather than shipping
// localhost on a tailnet deploy. These tests assert the config + script
// wiring that makes that impossible, so it can't silently regress.

// asunsetRoot resolves the repo root from this test file's location, so it
// works regardless of the test's cwd (other tests chdir into temp dirs).
func asunsetRoot(t *testing.T) string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	// <root>/tools/deploy/keycloak_init_test.go → <root>
	return filepath.Join(filepath.Dir(thisFile), "..", "..")
}

func readRepoFile(t *testing.T, rel string) string {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(asunsetRoot(t), rel))
	if err != nil {
		t.Fatalf("read %s: %v", rel, err)
	}
	return string(b)
}

func TestTailscaleOverlayThreadsHostToKeycloakInit(t *testing.T) {
	overlay := readRepoFile(t, "compose.tailscale.yml")

	// The asunset-web client URIs are derived from the tailnet host. Both
	// the primary (WEB_BASE_URL) and the authoritative fallback
	// (TAILSCALE_HOST) must reach the keycloak-init container — losing
	// either reintroduces the localhost-redirect-uri failure mode. The
	// ${WEB_BASE_URL:-…} default is the `asunset dev` loopback override:
	// unset on every real deployment, so the tailnet derivation stands.
	if !strings.Contains(overlay, "WEB_BASE_URL: ${WEB_BASE_URL:-https://${TAILSCALE_HOST}}") {
		t.Error("compose.tailscale.yml must set keycloak-init WEB_BASE_URL to ${WEB_BASE_URL:-https://${TAILSCALE_HOST}}")
	}
	if !strings.Contains(overlay, "TAILSCALE_HOST: ${TAILSCALE_HOST}") {
		t.Error("compose.tailscale.yml must pass TAILSCALE_HOST into keycloak-init (init.sh derives + guards on it)")
	}
}

func TestKeycloakInitDerivesAndGuardsWebBaseURL(t *testing.T) {
	script := readRepoFile(t, "infra/keycloak/init.sh")

	// Derives WEB_BASE_URL from the declared remote host (tailnet OR TLS)
	// when not already set — both overlays share the guard.
	if !strings.Contains(script, `REMOTE_HOST="${TAILSCALE_HOST:-${TLS_WEB_HOST:-}}"`) {
		t.Error("init.sh must treat TAILSCALE_HOST and TLS_WEB_HOST as the authoritative remote host")
	}
	if !strings.Contains(script, `WEB_BASE_URL="https://${REMOTE_HOST}"`) {
		t.Error("init.sh must derive WEB_BASE_URL from the remote host when unset")
	}
	// The TLS-mode flavor of the landmine: empty-host interpolation.
	if !strings.Contains(script, `"$WEB_BASE_URL" = "https://"`) {
		t.Error("init.sh must treat a bare 'https://' (empty host interpolation) as unset")
	}
	// Fails loud rather than configuring localhost URIs on a remote deploy.
	if !strings.Contains(script, "http://localhost*") || !strings.Contains(script, "FATAL") {
		t.Error("init.sh must fail loud (FATAL) if a remote deploy would leave localhost redirect URIs")
	}
	// Still performs the actual client rewrite (base URL always first in
	// the list; KC_DEV_WEB_ORIGINS appends — see the dev-origins test).
	if !strings.Contains(script, `WEB_REDIRECTS="\"$WEB_BASE_URL/*\""`) ||
		!strings.Contains(script, `redirectUris=[$WEB_REDIRECTS]`) {
		t.Error("init.sh must rewrite asunset-web redirectUris from the resolved WEB_BASE_URL")
	}
}

// Documents the landmine the guard exists for: the realm export ships
// localhost dev URIs on asunset-web. If this ever changes, the guard
// rationale should be revisited — but it must never be the value a tailnet
// deploy is left with.
func TestRealmExportShipsLocalhostWebDefaults(t *testing.T) {
	realm := readRepoFile(t, "infra/keycloak/realm-export.json")
	if !strings.Contains(realm, "localhost:5173") {
		t.Skip("realm export no longer ships localhost:5173 — revisit the keycloak-init guard rationale")
	}
}

func TestDevWebOriginsKnobCoversAllThreeLists(t *testing.T) {
	// Dev-against-live (rook's swat-01 flag): KC_DEV_WEB_ORIGINS must land
	// each origin in ALL THREE Keycloak validation lists — redirect,
	// web-origin, and post-logout (the ##-separated attribute) — or
	// sign-out 400s. And compose must actually pass the var through.
	script := readRepoFile(t, "infra/keycloak/init.sh")
	for _, must := range []string{
		"KC_DEV_WEB_ORIGINS",
		`WEB_REDIRECTS="$WEB_REDIRECTS,\"$_o/*\""`,
		`WEB_ORIGINS="$WEB_ORIGINS,\"$_o\""`,
		`WEB_POST_LOGOUT="$WEB_POST_LOGOUT##$_o/*"`,
	} {
		if !strings.Contains(script, must) {
			t.Errorf("init.sh missing dev-origin handling: %q", must)
		}
	}
	if !strings.Contains(readRepoFile(t, "compose.yml"), "KC_DEV_WEB_ORIGINS: ${KC_DEV_WEB_ORIGINS:-}") {
		t.Error("compose.yml must pass KC_DEV_WEB_ORIGINS into keycloak-init")
	}
}

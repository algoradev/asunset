package main

import (
	"strings"
	"testing"
)

// A7 token-storage hardening (kestrel's ruling under Avi's delegation):
// access token in memory only, refresh token never in browser storage,
// silent renew rides Keycloak's httpOnly SSO cookie, refresh-token
// rotation server-side, baseline CSP on the web tier. These guards
// MOVED WITH THE CODE when the kernel was extracted to
// packages/web-sdk (frontend-sdk-decision.md): the posture now lives in
// the SDK (where vitest additionally tests behavior, not just strings),
// and the reference app is pinned to CONSUME it rather than restate it.

func TestSDKAuthUsesInMemoryTokenStore(t *testing.T) {
	cfg := readRepoFile(t, "packages/web-sdk/src/config.ts")
	if !strings.Contains(cfg, "InMemoryWebStorage") {
		t.Error("web-sdk config must keep tokens in InMemoryWebStorage — never localStorage/sessionStorage")
	}
	if strings.Contains(cfg, "window.localStorage") {
		t.Error("web-sdk config must not reference window.localStorage for the user store")
	}
	if !strings.Contains(cfg, "silent_redirect_uri") {
		t.Error("web-sdk config must set silent_redirect_uri (SSO-cookie silent renew)")
	}
}

func TestReferenceAppConsumesTheKernel(t *testing.T) {
	// Dogfood pin: the reference app must not re-grow a local auth
	// implementation next to the SDK (the one-implementation rule).
	auth := readRepoFile(t, "apps/web/src/auth.ts")
	if !strings.Contains(auth, `createOidcConfig`) ||
		!strings.Contains(auth, `"@asunset/web-sdk"`) {
		t.Error("apps/web auth.ts must build its config via @asunset/web-sdk createOidcConfig")
	}
	if strings.Contains(auth, "userStore:") || strings.Contains(auth, "WebStorageStateStore") {
		t.Error("apps/web auth.ts must not carry its own token-store wiring — that's the SDK's")
	}
	if !strings.Contains(readRepoFile(t, "apps/web/vite.config.ts"), "@asunset/web-sdk") {
		t.Error("apps/web must alias @asunset/web-sdk (Option S source distribution)")
	}
}

func TestSilentRenewPageIsWired(t *testing.T) {
	if !strings.Contains(readRepoFile(t, "apps/web/silent-renew.html"), "silent-renew.ts") {
		t.Error("silent-renew.html must load the silent-renew callback module")
	}
	if !strings.Contains(readRepoFile(t, "apps/web/src/silent-renew.ts"), "runSilentRenewCallback") {
		t.Error("apps/web silent-renew.ts must delegate to the SDK's runSilentRenewCallback")
	}
	if !strings.Contains(readRepoFile(t, "packages/web-sdk/src/silent-renew.ts"), "signinSilentCallback") {
		t.Error("web-sdk silent-renew must call signinSilentCallback")
	}
	if !strings.Contains(readRepoFile(t, "apps/web/vite.config.ts"), "silent-renew.html") {
		t.Error("vite.config.ts must build silent-renew.html as an entry point")
	}
}

func TestRealmEnforcesRefreshTokenRotation(t *testing.T) {
	script := readRepoFile(t, "infra/keycloak/init.sh")
	if !strings.Contains(script, "revokeRefreshToken=true") ||
		!strings.Contains(script, "refreshTokenMaxReuse=0") {
		t.Error("init.sh must push refresh-token rotation (revokeRefreshToken=true, refreshTokenMaxReuse=0) on every start")
	}
}

func TestWebNginxShipsBaselineCSP(t *testing.T) {
	tmpl := readRepoFile(t, "apps/web/nginx.conf.template")
	for _, directive := range []string{
		"Content-Security-Policy",
		"default-src 'self'",
		"object-src 'none'",
		"frame-ancestors 'self'",
		"X-Content-Type-Options",
		"Referrer-Policy",
	} {
		if !strings.Contains(tmpl, directive) {
			t.Errorf("nginx.conf.template missing %q", directive)
		}
	}
	// Every location that sets its own add_header must repeat the CSP —
	// nginx add_header inheritance drops parent headers otherwise.
	if strings.Count(tmpl, "Content-Security-Policy") < 3 {
		t.Error("CSP must be repeated in each add_header-bearing location (nginx inheritance)")
	}
	if !strings.Contains(readRepoFile(t, "apps/web/Dockerfile"), "templates/default.conf.template") {
		t.Error("web Dockerfile must install nginx.conf.template via the envsubst templates dir")
	}
}

func TestCspExtraOriginsWiredPerMode(t *testing.T) {
	if !strings.Contains(readRepoFile(t, "compose.yml"), "CSP_EXTRA_ORIGINS: ${CSP_EXTRA_ORIGINS:-") {
		t.Error("compose.yml must default CSP_EXTRA_ORIGINS for plain mode")
	}
	if !strings.Contains(readRepoFile(t, "compose.tailscale.yml"), `CSP_EXTRA_ORIGINS: ""`) {
		t.Error("compose.tailscale.yml must set CSP_EXTRA_ORIGINS empty (single origin)")
	}
	if !strings.Contains(readRepoFile(t, "compose.tls.yml"), "CSP_EXTRA_ORIGINS: https://${TLS_AUTH_HOST} https://${TLS_API_HOST}") {
		t.Error("compose.tls.yml must allow the auth+api origins in CSP")
	}
}

package main

import (
	"strings"
	"testing"
)

// A7 token-storage hardening (kestrel's ruling under Avi's delegation):
// access token in memory only, refresh token never in browser storage,
// silent renew rides Keycloak's httpOnly SSO cookie, refresh-token
// rotation server-side, baseline CSP on the web tier. These tests pin
// the wiring so a refactor can't silently regress any leg of it.

func TestWebAuthUsesInMemoryTokenStore(t *testing.T) {
	auth := readRepoFile(t, "apps/web/src/auth.ts")
	if !strings.Contains(auth, "InMemoryWebStorage") {
		t.Error("auth.ts must keep tokens in InMemoryWebStorage — never localStorage/sessionStorage")
	}
	if strings.Contains(auth, "window.localStorage") {
		t.Error("auth.ts must not reference window.localStorage for the user store")
	}
	if !strings.Contains(auth, "silent_redirect_uri") {
		t.Error("auth.ts must configure silent_redirect_uri (SSO-cookie silent renew)")
	}
}

func TestSilentRenewPageIsWired(t *testing.T) {
	if !strings.Contains(readRepoFile(t, "apps/web/silent-renew.html"), "silent-renew.ts") {
		t.Error("silent-renew.html must load the silent-renew callback module")
	}
	if !strings.Contains(readRepoFile(t, "apps/web/src/silent-renew.ts"), "signinSilentCallback") {
		t.Error("silent-renew.ts must call signinSilentCallback")
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

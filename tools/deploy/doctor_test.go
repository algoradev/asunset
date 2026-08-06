package main

import (
	"strings"
	"testing"
)

// Every static doctor check exists because a real incident produced it —
// each test names its incident.

func results(vars map[string]string) map[string]checkResult {
	out := map[string]checkResult{}
	for _, r := range doctorStaticChecks(vars) {
		out[r.Name] = r
	}
	return out
}

func healthyPlain() map[string]string {
	return map[string]string{
		"ASUNSET_MODE":                  "plain",
		"KEYCLOAK_PUBLIC_URL":           "http://localhost:8080",
		"VITE_KEYCLOAK_URL":             "http://localhost:8080",
		"KEYCLOAK_INTERNAL_URL":         "http://keycloak:8080",
		"SESSION_TOKEN_PRIVATE_KEY_B64": "abc",
	}
}

func TestHealthyPlainEnvPasses(t *testing.T) {
	for name, r := range results(healthyPlain()) {
		if r.Status == statusFail {
			t.Errorf("%s failed on a healthy plain env: %s", name, r.Detail)
		}
	}
}

func TestStaleIssuerSplitFails(t *testing.T) {
	// Incident: the repo .env carried a tailnet KEYCLOAK_PUBLIC_URL while
	// the stack ran plain — every authenticated request 401'd, and the
	// web bundle baked the wrong URL. Two different symptoms, one cause.
	v := healthyPlain()
	v["VITE_KEYCLOAK_URL"] = "https://old-laptop.tailnet.ts.net/auth"
	if r := results(v)["issuer-coherence"]; r.Status != statusFail {
		t.Errorf("split public/vite issuer must FAIL, got %s", r.Status)
	}
}

func TestAuthSuffixDriftFails(t *testing.T) {
	// Incident: centum's B-KCURL — bare internal URL in a path-routed
	// mode → JWKS 404 → HTTP 500 on every authenticated request.
	v := map[string]string{
		"ASUNSET_MODE":          "tailscale",
		"TAILSCALE_HOST":        "box.tailnet.ts.net",
		"KEYCLOAK_PUBLIC_URL":   "https://box.tailnet.ts.net/auth",
		"VITE_KEYCLOAK_URL":     "https://box.tailnet.ts.net/auth",
		"KEYCLOAK_INTERNAL_URL": "http://keycloak:8080", // missing /auth
	}
	if r := results(v)["internal-url"]; r.Status != statusFail {
		t.Errorf("missing /auth in tailscale mode must FAIL, got %s", r.Status)
	}
	v["KEYCLOAK_INTERNAL_URL"] = "http://keycloak:8080/auth"
	if r := results(v)["internal-url"]; r.Status != statusOK {
		t.Errorf("correct /auth should pass, got %s: %s", r.Status, r.Detail)
	}
	// And the inverse: /auth in plain mode is the same 404 mirrored.
	p := healthyPlain()
	p["KEYCLOAK_INTERNAL_URL"] = "http://keycloak:8080/auth"
	if r := results(p)["internal-url"]; r.Status != statusFail {
		t.Errorf("/auth suffix in plain mode must FAIL, got %s", r.Status)
	}
}

func TestTailscaleHostChecks(t *testing.T) {
	// Incident: wirebit's first bootstrap — tailnet deploy whose env
	// didn't thread the host; keycloak-init now FATALs, doctor should
	// name it BEFORE the boot.
	v := map[string]string{
		"ASUNSET_MODE":          "tailscale",
		"KEYCLOAK_PUBLIC_URL":   "https://box.tailnet.ts.net/auth",
		"VITE_KEYCLOAK_URL":     "https://box.tailnet.ts.net/auth",
		"KEYCLOAK_INTERNAL_URL": "http://keycloak:8080/auth",
	}
	if r := results(v)["remote-host"]; r.Status != statusFail {
		t.Errorf("tailscale mode without TAILSCALE_HOST must FAIL, got %s", r.Status)
	}
	v["TAILSCALE_HOST"] = "other-box.tailnet.ts.net"
	if r := results(v)["remote-host"]; r.Status != statusFail {
		t.Errorf("public URL not containing TAILSCALE_HOST must FAIL, got %s", r.Status)
	}
	// Leftover tailnet var on a local setup: warn, not fail.
	p := healthyPlain()
	p["TAILSCALE_HOST"] = "old-laptop.tailnet.ts.net"
	if r := results(p)["remote-host"]; r.Status != statusWarn {
		t.Errorf("leftover TAILSCALE_HOST on local env should WARN, got %s", r.Status)
	}
}

func TestEphemeralSessionKeyWarns(t *testing.T) {
	// Incident-class: sessions silently dying on every api restart.
	v := healthyPlain()
	delete(v, "SESSION_TOKEN_PRIVATE_KEY_B64")
	if r := results(v)["session-key"]; r.Status != statusWarn {
		t.Errorf("missing session key should WARN, got %s", r.Status)
	}
}

func TestAsunsetEnvStaticCheck(t *testing.T) {
	find := func(vars map[string]string) checkResult {
		for _, r := range doctorStaticChecks(vars) {
			if r.Name == "asunset-env" {
				return r
			}
		}
		t.Fatal("asunset-env check missing")
		return checkResult{}
	}
	if r := find(map[string]string{"ASUNSET_ENV": "prod"}); r.Status != statusOK {
		t.Errorf("prod should be ok, got %s (%s)", r.Status, r.Detail)
	}
	if r := find(map[string]string{}); r.Status != statusOK {
		t.Errorf("unset should be ok (compose defaults dev), got %s", r.Status)
	}
	// The named incident: "production" is not in the Literal and kills
	// the api at boot — doctor must catch it PRE-deploy.
	if r := find(map[string]string{"ASUNSET_ENV": "production"}); r.Status != statusFail {
		t.Errorf("invalid value must FAIL, got %s (%s)", r.Status, r.Detail)
	}
}

func TestComposeDefaultsAsunsetEnv(t *testing.T) {
	// The 663c527331f7 trap: defaultless ${ASUNSET_ENV} renders a
	// present-but-empty env var, which pydantic refuses (the field's
	// own default never applies). The compose default is the fix.
	if !strings.Contains(readRepoFile(t, "compose.yml"), "ASUNSET_ENV: ${ASUNSET_ENV:-dev}") {
		t.Error("compose.yml must default ASUNSET_ENV (empty-present kills the api at boot)")
	}
}

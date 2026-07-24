package main

import (
	"regexp"
	"strings"
	"testing"
)

var nextServiceRe = regexp.MustCompile(`\n  [a-z][a-z0-9-]*:`)

// Regression guard for the co-host port exposure (OpsRoom arc, A6):
// tailscale mode's posture is "nothing publishes except Caddy on
// loopback", but the base compose file publishes Postgres (5432) and
// OpenFGA (8081/8083) on 0.0.0.0 and the overlay originally reset only
// keycloak/api/web. On a host without an external firewall that left the
// data plane exposed; on a shared host it guaranteed a 5432 collision.
// These tests pin the overlay resets and the cohost overlay's
// loopback-or-nothing defaults so neither can silently regress.

func TestRemoteOverlaysResetDataPlanePorts(t *testing.T) {
	// Both remote-facing overlays must stop the data plane publishing —
	// tailscale AND TLS (the latter faces the open internet in acme mode).
	for _, file := range []string{"compose.tailscale.yml", "compose.tls.yml"} {
		overlay := readRepoFile(t, file)
		for _, svc := range []string{"postgres", "openfga"} {
			idx := strings.Index(overlay, "\n  "+svc+":")
			if idx < 0 {
				t.Errorf("%s must define a %s service block to reset its ports", file, svc)
				continue
			}
			block := overlay[idx:]
			if m := nextServiceRe.FindStringIndex(block[3:]); m != nil {
				block = block[:m[0]+3]
			}
			if !strings.Contains(block, "ports: !reset []") {
				t.Errorf("%s %s block must contain `ports: !reset []` — without it the base 0.0.0.0 binding survives on remote deploys", file, svc)
			}
		}
	}
}

func TestLongRunningServicesHaveRestartPolicies(t *testing.T) {
	// Live incident: openfga (no restart policy) exited and stayed dead
	// for days while api crash-looped behind it. Every long-running
	// service must declare a restart policy; one-shots stay "no".
	base := readRepoFile(t, "compose.yml")
	for _, svc := range []string{"postgres", "keycloak", "openfga", "vector", "api", "web"} {
		idx := strings.Index(base, "\n  "+svc+":")
		if idx < 0 {
			t.Errorf("compose.yml missing expected service %s", svc)
			continue
		}
		// Bound the block at the next top-level service key ("\n  x:"
		// where x starts a two-space-indented identifier).
		block := base[idx+1:]
		if m := nextServiceRe.FindStringIndex(block[3:]); m != nil {
			block = block[:m[0]+3]
		}
		if !strings.Contains(block, "restart: unless-stopped") {
			t.Errorf("compose.yml %s must declare restart: unless-stopped", svc)
		}
	}
}

func TestCohostOverlayBindsLoopbackWithNonDefaultPorts(t *testing.T) {
	overlay := readRepoFile(t, "compose.cohost.yml")

	// Loopback default, parameterized bind, non-colliding host ports.
	if !strings.Contains(overlay, "${ASUNSET_BIND:-127.0.0.1}:${ASUNSET_PG_PORT:-15432}:5432") {
		t.Error("compose.cohost.yml postgres must publish via ${ASUNSET_BIND:-127.0.0.1}:${ASUNSET_PG_PORT:-15432}")
	}
	if !strings.Contains(overlay, "${ASUNSET_BIND:-127.0.0.1}:${ASUNSET_FGA_PORT:-18081}:8080") {
		t.Error("compose.cohost.yml openfga must publish via ${ASUNSET_BIND:-127.0.0.1}:${ASUNSET_FGA_PORT:-18081}")
	}

	// Port lists MERGE (append) across compose files — without !override
	// the base file's 0.0.0.0 bindings would survive alongside these.
	if strings.Count(overlay, "ports: !override") != 2 {
		t.Error("compose.cohost.yml must use `ports: !override` on both services — plain ports: merges with (not replaces) the base bindings")
	}

	// The tightest posture must stay reachable: metrics not published.
	if strings.Contains(overlay, ":2112") && !strings.Contains(overlay, "# Metrics (2112) intentionally not published") {
		t.Error("compose.cohost.yml must not publish OpenFGA metrics (2112) by default")
	}
}

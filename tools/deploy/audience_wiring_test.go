package main

import (
	"strings"
	"testing"
)

// Identity-contract D6 (aud array): additional resource servers get their
// own audience entry in asunset-web access tokens, driven by
// KEYCLOAK_EXTRA_AUDIENCES. These tests pin the wiring so a compose or
// script refactor can't silently drop the mechanism — a dropped mapper
// surfaces only as a 401 "wrong audience" at the downstream RS.

func TestComposeThreadsExtraAudiencesToKeycloakInit(t *testing.T) {
	base := readRepoFile(t, "compose.yml")
	if !strings.Contains(base, "KEYCLOAK_EXTRA_AUDIENCES: ${KEYCLOAK_EXTRA_AUDIENCES:-}") {
		t.Error("compose.yml must thread KEYCLOAK_EXTRA_AUDIENCES into keycloak-init")
	}
	env := readRepoFile(t, ".env.example")
	if !strings.Contains(env, "KEYCLOAK_EXTRA_AUDIENCES=") {
		t.Error(".env.example must document KEYCLOAK_EXTRA_AUDIENCES")
	}
}

func TestInitScriptCreatesCustomAudienceMappers(t *testing.T) {
	script := readRepoFile(t, "infra/keycloak/init.sh")

	// Custom audience (arbitrary strings), not client audience — D6
	// explicitly avoids per-RS Keycloak clients.
	if !strings.Contains(script, `config."included.custom.audience"=`) {
		t.Error("init.sh must use included.custom.audience — RS audiences are strings, not clients")
	}
	// Access token only; identity tokens don't carry RS audiences.
	if !strings.Contains(script, `config."access.token.claim"=true`) ||
		!strings.Contains(script, `config."id.token.claim"=false`) {
		t.Error("init.sh audience mappers must be access-token-only")
	}
	// Idempotency: mapper existence is checked by name before create.
	if !strings.Contains(script, "audience-$AUD") {
		t.Error("init.sh must name mappers audience-<value> and skip existing ones")
	}
}

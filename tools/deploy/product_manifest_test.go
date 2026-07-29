package main

// The product deploy manifest is a contract surface (report 95): these
// pin the fail-loud validation (relay guard 1), the coherence gate
// (trap #3 made structural), and generate-idempotency (one root .env,
// one writer, never rotate on re-init).

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeManifest(t *testing.T, root, body string, files ...string) {
	t.Helper()
	for _, f := range files {
		p := filepath.Join(root, f)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte("x"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(root, productManifestName), []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}

const validManifest = `version: 1
name: opsroom
compose: deploy/compose.product.yml
caddyfile:
  tailscale: deploy/Caddyfile
env:
  generate: [OPSROOM_PG_PASSWORD]
init: opsroom-init
doctor: opsroom-doctor
`

func TestManifestParsesAndValidates(t *testing.T) {
	root := t.TempDir()
	writeManifest(t, root, validManifest, "deploy/compose.product.yml", "deploy/Caddyfile")
	m, err := loadProductManifest(root)
	if err != nil {
		t.Fatal(err)
	}
	if m.Name != "opsroom" || m.Init != "opsroom-init" || m.Doctor != "opsroom-doctor" {
		t.Errorf("fields lost in parse: %+v", m)
	}
	if len(m.Env.Generate) != 1 || m.Env.Generate[0] != "OPSROOM_PG_PASSWORD" {
		t.Errorf("env.generate lost: %+v", m.Env)
	}
}

func TestManifestAbsentIsNotAnError(t *testing.T) {
	m, err := loadProductManifest(t.TempDir())
	if err != nil || m != nil {
		t.Errorf("absent manifest must be (nil, nil), got (%v, %v)", m, err)
	}
}

func TestManifestFailsLoud(t *testing.T) {
	cases := []struct {
		name, body, want string
		files            []string
	}{
		{"unknown key", "version: 1\nname: x\ncompose: c.yml\nprompts: [ORG]\n",
			"unknown key", []string{"c.yml"}},
		{"wrong version", strings.Replace(validManifest, "version: 1", "version: 2", 1),
			"version 2 not supported", []string{"deploy/compose.product.yml", "deploy/Caddyfile"}},
		{"missing compose file", validManifest, "not found", []string{"deploy/Caddyfile"}},
		{"unknown mode", strings.Replace(validManifest, "tailscale:", "plain:", 1),
			"unknown mode", []string{"deploy/compose.product.yml", "deploy/Caddyfile"}},
		{"no name", "version: 1\ncompose: c.yml\n", "name is required", []string{"c.yml"}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			root := t.TempDir()
			writeManifest(t, root, c.body, c.files...)
			_, err := loadProductManifest(root)
			if err == nil || !strings.Contains(err.Error(), c.want) {
				t.Errorf("want error containing %q, got %v", c.want, err)
			}
		})
	}
}

func TestCaddyfileCoherenceGate(t *testing.T) {
	root := t.TempDir()
	writeManifest(t, root, validManifest, "deploy/compose.product.yml", "deploy/Caddyfile")
	m, err := loadProductManifest(root)
	if err != nil {
		t.Fatal(err)
	}
	// Declared mode: passes.
	if p, err := m.CaddyfileFor(ModeTailscale); err != nil || p != "deploy/Caddyfile" {
		t.Errorf("tailscale should resolve, got (%q, %v)", p, err)
	}
	// Undeclared caddy-bearing mode: the refusal (trap #3, structural).
	if _, err := m.CaddyfileFor(ModeTLSAcme); err == nil ||
		!strings.Contains(err.Error(), "no caddyfile entry") {
		t.Errorf("tls-acme must refuse without an entry, got %v", err)
	}
	// Plain mode has no caddy — never gated.
	if _, err := m.CaddyfileFor(ModePlain); err != nil {
		t.Errorf("plain must never gate, got %v", err)
	}
	// No map at all = paved-path consumer; generated Caddyfile stands.
	m2 := &ProductManifest{Version: 1, Name: "x", Compose: "c"}
	if _, err := m2.CaddyfileFor(ModeTLSAcme); err != nil {
		t.Errorf("no-map consumers must not gate, got %v", err)
	}
}

func TestProductSecretsGenerateOnceNeverRotate(t *testing.T) {
	root := t.TempDir()
	envPath := filepath.Join(root, ".env")
	if err := os.WriteFile(envPath, []byte("ASUNSET_MODE=tailscale\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	m := &ProductManifest{Env: ManifestEnv{Generate: []string{"OPSROOM_PG_PASSWORD", "OTHER_KEY"}}}

	added, err := ensureProductSecrets(envPath, m)
	if err != nil || len(added) != 2 {
		t.Fatalf("first run should add both, got (%v, %v)", added, err)
	}
	first, _ := os.ReadFile(envPath)
	if !strings.Contains(string(first), productSecretHeader) {
		t.Error("labeled block header missing")
	}

	// Second run: nothing added, values untouched (never rotate).
	added, err = ensureProductSecrets(envPath, m)
	if err != nil || len(added) != 0 {
		t.Fatalf("second run must be a no-op, got (%v, %v)", added, err)
	}
	second, _ := os.ReadFile(envPath)
	if string(first) != string(second) {
		t.Error("re-run rotated or rewrote product secrets")
	}
}

func TestDevLoopbackURLs(t *testing.T) {
	cfg := Config{Mode: ModeTailscale, DevLoopback: true}
	if cfg.AuthURL() != "http://127.0.0.1:5173/auth" {
		t.Errorf("dev AuthURL = %s", cfg.AuthURL())
	}
	if cfg.WebURL() != "http://127.0.0.1:5173" {
		t.Errorf("dev WebURL = %s", cfg.WebURL())
	}
	// The overlay's loopback overrides must stay default-able (unset →
	// tailnet derivation exactly as before).
	overlay := readRepoFile(t, "compose.tailscale.yml")
	for _, must := range []string{
		"${WEB_BASE_URL:-https://${TAILSCALE_HOST}}",
		"${KC_BASE_URL:-https://${TAILSCALE_HOST}}/auth",
	} {
		if !strings.Contains(overlay, must) {
			t.Errorf("compose.tailscale.yml lost the default-able override %q", must)
		}
	}
}

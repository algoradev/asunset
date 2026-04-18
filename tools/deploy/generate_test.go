package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Headless smoke tests for every deployment mode. Exercises secret gen +
// file generation; skips the huh forms (which need a TTY).

func withRepoRoot(t *testing.T, body func(root string)) {
	t.Helper()
	tmp := t.TempDir()
	// The wizard locates the repo root by walking up until it finds
	// compose.yml. Drop a stub there.
	if err := os.WriteFile(filepath.Join(tmp, "compose.yml"), []byte("# stub\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	origWd, _ := os.Getwd()
	if err := os.Chdir(tmp); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chdir(origWd) })
	body(tmp)
}

func generatedEnv(t *testing.T, root string) string {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(root, ".env"))
	if err != nil {
		t.Fatalf("read .env: %v", err)
	}
	return string(b)
}

func generatedCaddyfile(t *testing.T, root string) string {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(root, "infra", "caddy", "Caddyfile"))
	if err != nil {
		t.Fatalf("read Caddyfile: %v", err)
	}
	return string(b)
}

func buildConfig(mode Mode) Config {
	cfg := newConfig()
	cfg.Mode = mode
	cfg.WebHost = "asunset.example.com"
	cfg.AuthHost = "auth.asunset.example.com"
	cfg.APIHost = "api.asunset.example.com"
	cfg.CertPath = "/etc/ssl/asunset/fullchain.pem"
	cfg.KeyPath = "/etc/ssl/asunset/privkey.pem"
	cfg.AcmeEmail = "ops@example.com"
	return cfg
}

func mustGenerate(t *testing.T, cfg *Config) {
	t.Helper()
	if err := generateSecrets(cfg); err != nil {
		t.Fatalf("generateSecrets: %v", err)
	}
	if err := writeConfigFiles(cfg); err != nil {
		t.Fatalf("writeConfigFiles: %v", err)
	}
}

func TestPlainMode(t *testing.T) {
	withRepoRoot(t, func(root string) {
		cfg := buildConfig(ModePlain)
		mustGenerate(t, &cfg)
		env := generatedEnv(t, root)

		// Secrets were populated and landed in .env.
		if !strings.Contains(env, "KEYCLOAK_ADMIN_PASSWORD="+cfg.Secrets.KeycloakAdminPass) {
			t.Fatal("KEYCLOAK_ADMIN_PASSWORD not substituted")
		}
		if !strings.Contains(env, "OPENFGA_API_KEY="+cfg.Secrets.OpenFGAAPIKey) {
			t.Fatal("OPENFGA_API_KEY not substituted")
		}
		// Plain mode: localhost URLs, no TLS_* section.
		if !strings.Contains(env, "VITE_API_URL=http://localhost:8000") {
			t.Fatal("expected localhost API URL in plain mode")
		}
		if strings.Contains(env, "TLS_WEB_HOST=") {
			t.Fatal("TLS_WEB_HOST should not appear in plain mode")
		}
		// No Caddyfile in plain mode.
		if _, err := os.Stat(filepath.Join(root, "infra", "caddy", "Caddyfile")); err == nil {
			t.Fatal("Caddyfile should not exist in plain mode")
		}
	})
}

func TestTLSInternalMode(t *testing.T) {
	withRepoRoot(t, func(root string) {
		cfg := buildConfig(ModeTLSInternal)
		mustGenerate(t, &cfg)

		env := generatedEnv(t, root)
		if !strings.Contains(env, "VITE_API_URL=https://api.asunset.example.com") {
			t.Fatal("expected https API URL")
		}
		if !strings.Contains(env, "TLS_WEB_HOST=asunset.example.com") {
			t.Fatal("expected TLS_WEB_HOST in .env")
		}

		caddy := generatedCaddyfile(t, root)
		if !strings.Contains(caddy, "local_certs") {
			t.Fatal("expected local_certs in internal-mode Caddyfile")
		}
		if !strings.Contains(caddy, "asunset.example.com") {
			t.Fatal("hostname not substituted into Caddyfile")
		}
		if !strings.Contains(caddy, "reverse_proxy web:80") {
			t.Fatal("missing web upstream in Caddyfile")
		}
	})
}

func TestTLSOperatorMode(t *testing.T) {
	withRepoRoot(t, func(root string) {
		cfg := buildConfig(ModeTLSOperator)
		mustGenerate(t, &cfg)

		caddy := generatedCaddyfile(t, root)
		if !strings.Contains(caddy, "tls /etc/ssl/asunset/fullchain.pem /etc/ssl/asunset/privkey.pem") {
			t.Fatalf("cert paths not substituted:\n%s", caddy)
		}
		if strings.Contains(caddy, "local_certs") {
			t.Fatal("operator mode should not use local_certs")
		}
		if strings.Contains(caddy, "{CertPath}") {
			t.Fatal("template placeholder not substituted")
		}
	})
}

func TestTLSAcmeMode(t *testing.T) {
	withRepoRoot(t, func(root string) {
		cfg := buildConfig(ModeTLSAcme)
		mustGenerate(t, &cfg)

		caddy := generatedCaddyfile(t, root)
		if !strings.Contains(caddy, "email ops@example.com") {
			t.Fatalf("ACME email not substituted:\n%s", caddy)
		}
		if strings.Contains(caddy, "local_certs") {
			t.Fatal("ACME mode should not use local_certs")
		}
	})
}

func buildTailscaleConfig() Config {
	cfg := buildConfig(ModeTailscale)
	cfg.TailscaleHost = "asunset.tail-abc123.ts.net"
	return cfg
}

func TestTailscaleMode(t *testing.T) {
	withRepoRoot(t, func(root string) {
		cfg := buildTailscaleConfig()
		mustGenerate(t, &cfg)

		env := generatedEnv(t, root)
		if !strings.Contains(env, "VITE_API_URL=https://asunset.tail-abc123.ts.net/api") {
			t.Fatalf("expected path-prefixed API URL:\n%s", env)
		}
		if !strings.Contains(env, "VITE_KEYCLOAK_URL=https://asunset.tail-abc123.ts.net/auth") {
			t.Fatal("expected path-prefixed Keycloak URL")
		}
		if !strings.Contains(env, "TAILSCALE_HOST=asunset.tail-abc123.ts.net") {
			t.Fatal("expected TAILSCALE_HOST env var")
		}
		if strings.Contains(env, "TLS_WEB_HOST=") {
			t.Fatal("Tailscale mode should not emit TLS_* vars")
		}

		caddy := generatedCaddyfile(t, root)
		if !strings.Contains(caddy, ":5173") {
			t.Fatal("expected Caddy listening on :5173 for tailscale")
		}
		if strings.Contains(caddy, "tls ") || strings.Contains(caddy, "local_certs") {
			t.Fatal("Tailscale Caddyfile should not declare TLS")
		}
		if !strings.Contains(caddy, "handle /auth/*") {
			t.Fatal("missing /auth/* route in Tailscale Caddyfile")
		}
		if !strings.Contains(caddy, "handle_path /api/*") {
			t.Fatal("missing /api/* route in Tailscale Caddyfile")
		}
	})
}

func TestSecretsAreUnique(t *testing.T) {
	// Paranoia: make sure we're not seeding rand badly.
	seen := map[string]struct{}{}
	for i := 0; i < 20; i++ {
		s, err := randString(32)
		if err != nil {
			t.Fatal(err)
		}
		if _, dup := seen[s]; dup {
			t.Fatalf("duplicate secret generated: %s", s)
		}
		seen[s] = struct{}{}
	}
}

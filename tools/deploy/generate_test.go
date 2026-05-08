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
		// ASUNSET_MODE stamp is the canonical signal for lifecycle cmds.
		if !strings.Contains(env, "ASUNSET_MODE=plain") {
			t.Fatal("ASUNSET_MODE=plain not stamped into .env")
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
		if !strings.Contains(env, "ASUNSET_MODE=tailscale") {
			t.Fatal("ASUNSET_MODE=tailscale not stamped into .env")
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

// withConsumerLayout simulates a vendored deployment: consumer repo
// root contains compose.product.yml and a vendor/asunset/ subtree with
// the asunset compose.yml. The CLI should detect this layout and write
// .env at the consumer root, plus auto-include the product overlay in
// composeArgs.
func withConsumerLayout(t *testing.T, body func(consumerRoot, asunsetRoot string)) {
	t.Helper()
	consumerRoot := t.TempDir()
	asunsetRoot := filepath.Join(consumerRoot, "vendor", "asunset")
	if err := os.MkdirAll(asunsetRoot, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(asunsetRoot, "compose.yml"), []byte("# stub\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(consumerRoot, "compose.product.yml"), []byte("# stub\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	origWd, _ := os.Getwd()
	if err := os.Chdir(asunsetRoot); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chdir(origWd) })
	body(consumerRoot, asunsetRoot)
}

func TestConsumerLayoutDetected(t *testing.T) {
	withConsumerLayout(t, func(consumerRoot, asunsetRoot string) {
		layout, err := detectLayout()
		if err != nil {
			t.Fatalf("detectLayout: %v", err)
		}
		if !layout.Vendored {
			t.Fatal("expected Vendored=true")
		}
		if layout.AsunsetRoot != asunsetRoot {
			t.Fatalf("AsunsetRoot: got %q want %q", layout.AsunsetRoot, asunsetRoot)
		}
		if layout.ConsumerRoot != consumerRoot {
			t.Fatalf("ConsumerRoot: got %q want %q", layout.ConsumerRoot, consumerRoot)
		}
		want := filepath.Join(consumerRoot, "compose.product.yml")
		if layout.ProductOverlay != want {
			t.Fatalf("ProductOverlay: got %q want %q", layout.ProductOverlay, want)
		}
		if layout.EnvPath() != filepath.Join(consumerRoot, ".env") {
			t.Fatalf("EnvPath: got %q", layout.EnvPath())
		}
	})
}

func TestConsumerLayoutEnvWritesAtConsumerRoot(t *testing.T) {
	withConsumerLayout(t, func(consumerRoot, asunsetRoot string) {
		cfg := buildConfig(ModePlain)
		mustGenerate(t, &cfg)
		if _, err := os.Stat(filepath.Join(consumerRoot, ".env")); err != nil {
			t.Fatalf("expected .env at consumer root: %v", err)
		}
		if _, err := os.Stat(filepath.Join(asunsetRoot, ".env")); !os.IsNotExist(err) {
			t.Fatalf("expected NO .env inside vendor/asunset; got err=%v", err)
		}
	})
}

func TestConsumerLayoutComposeArgsIncludeOverlay(t *testing.T) {
	withConsumerLayout(t, func(consumerRoot, _ string) {
		cfg := buildConfig(ModePlain)
		args := composeArgs(&cfg, "up", "-d")
		joined := strings.Join(args, " ")
		envPath := filepath.Join(consumerRoot, ".env")
		overlay := filepath.Join(consumerRoot, "compose.product.yml")
		if !strings.Contains(joined, "--env-file "+envPath) {
			t.Fatalf("composeArgs missing --env-file %s; got: %s", envPath, joined)
		}
		if !strings.Contains(joined, "-f "+overlay) {
			t.Fatalf("composeArgs missing -f %s; got: %s", overlay, joined)
		}
	})
}

func TestStandaloneLayoutComposeArgsHaveNoOverlay(t *testing.T) {
	withRepoRoot(t, func(root string) {
		cfg := buildConfig(ModePlain)
		args := composeArgs(&cfg, "up", "-d")
		joined := strings.Join(args, " ")
		if strings.Contains(joined, "compose.product.yml") {
			t.Fatalf("standalone layout shouldn't include product overlay; got: %s", joined)
		}
		if !strings.Contains(joined, "--env-file "+filepath.Join(root, ".env")) {
			t.Fatalf("composeArgs missing --env-file; got: %s", joined)
		}
	})
}

func TestKeycloakInternalURLByMode(t *testing.T) {
	cases := []struct {
		mode Mode
		want string
	}{
		{ModePlain, "http://keycloak:8080"},
		{ModeTLSInternal, "http://keycloak:8080"},
		{ModeTLSOperator, "http://keycloak:8080"},
		{ModeTLSAcme, "http://keycloak:8080"},
		{ModeTailscale, "http://keycloak:8080/auth"},
	}
	for _, tc := range cases {
		cfg := Config{Mode: tc.mode}
		if got := cfg.KeycloakInternalURL(); got != tc.want {
			t.Errorf("mode=%s: got %q want %q", tc.mode, got, tc.want)
		}
	}
}

func TestEnvFileEmbedsKeycloakInternalURL(t *testing.T) {
	withRepoRoot(t, func(root string) {
		cfg := buildConfig(ModeTailscale)
		cfg.TailscaleHost = "demo.tail-abc.ts.net"
		mustGenerate(t, &cfg)
		env := generatedEnv(t, root)
		if !strings.Contains(env, "KEYCLOAK_INTERNAL_URL=http://keycloak:8080/auth") {
			t.Fatalf("tailscale .env missing /auth-suffixed KEYCLOAK_INTERNAL_URL; got:\n%s", env)
		}
	})
	withRepoRoot(t, func(root string) {
		cfg := buildConfig(ModeTLSAcme)
		mustGenerate(t, &cfg)
		env := generatedEnv(t, root)
		if !strings.Contains(env, "KEYCLOAK_INTERNAL_URL=http://keycloak:8080\n") {
			t.Fatalf("TLS .env should keep bare KEYCLOAK_INTERNAL_URL; got:\n%s", env)
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

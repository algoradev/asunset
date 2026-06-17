package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// End-to-end non-interactive runs exercise parse → build → validate →
// resolveSecrets → write, the same chain cmdInitNonInteractive drives, minus
// the --yes gate and stdout. These prove unattended generation matches the
// wizard's output for the same inputs.

func runNonInteractive(t *testing.T, args []string) Config {
	t.Helper()
	opts, err := parseInitArgs(args)
	if err != nil {
		t.Fatalf("parseInitArgs(%v): %v", args, err)
	}
	cfg, err := buildConfigFromOptions(opts)
	if err != nil {
		t.Fatalf("buildConfigFromOptions: %v", err)
	}
	if err := validateConfig(&cfg); err != nil {
		t.Fatalf("validateConfig: %v", err)
	}
	existing, err := loadExistingEnv()
	if err != nil {
		t.Fatalf("loadExistingEnv: %v", err)
	}
	if err := resolveSecrets(&cfg, opts, existing); err != nil {
		t.Fatalf("resolveSecrets: %v", err)
	}
	if err := writeConfigFiles(&cfg); err != nil {
		t.Fatalf("writeConfigFiles: %v", err)
	}
	return cfg
}

func TestNonInteractivePlain(t *testing.T) {
	withRepoRoot(t, func(root string) {
		cfg := runNonInteractive(t, []string{"--mode", "plain", "--yes"})
		env := generatedEnv(t, root)
		if !strings.Contains(env, "ASUNSET_MODE=plain") {
			t.Fatal("ASUNSET_MODE=plain not stamped")
		}
		if !strings.Contains(env, "VITE_API_URL=http://localhost:8000") {
			t.Fatal("expected localhost API URL")
		}
		// Secrets were generated and landed in .env.
		if cfg.Secrets.OpenFGAAPIKey == "" || !strings.Contains(env, "OPENFGA_API_KEY="+cfg.Secrets.OpenFGAAPIKey) {
			t.Fatal("OpenFGA key not generated/written")
		}
		if _, err := os.Stat(filepath.Join(root, "infra", "caddy", "Caddyfile")); err == nil {
			t.Fatal("plain mode should not write a Caddyfile")
		}
	})
}

func TestNonInteractiveTailscale(t *testing.T) {
	withRepoRoot(t, func(root string) {
		runNonInteractive(t, []string{
			"--mode", "tailscale",
			"--tailscale-host", "crm.tail-abc.ts.net",
			"--yes",
		})
		env := generatedEnv(t, root)
		if !strings.Contains(env, "TAILSCALE_HOST=crm.tail-abc.ts.net") {
			t.Fatalf("TAILSCALE_HOST not written:\n%s", env)
		}
		if !strings.Contains(env, "VITE_API_URL=https://crm.tail-abc.ts.net/api") {
			t.Fatal("expected path-prefixed API URL")
		}
		caddy := generatedCaddyfile(t, root)
		if !strings.Contains(caddy, ":5173") {
			t.Fatal("expected Caddy :5173 in tailscale mode")
		}
	})
}

func TestNonInteractiveTLSOperatorFlags(t *testing.T) {
	withRepoRoot(t, func(root string) {
		runNonInteractive(t, []string{
			"--mode", "tls-operator",
			"--web-host", "w.example.com",
			"--auth-host", "a.example.com",
			"--api-host", "p.example.com",
			"--cert-path", "/etc/ssl/full.pem",
			"--key-path", "/etc/ssl/key.pem",
			"--yes",
		})
		caddy := generatedCaddyfile(t, root)
		if !strings.Contains(caddy, "tls /etc/ssl/full.pem /etc/ssl/key.pem") {
			t.Fatalf("cert paths not in Caddyfile:\n%s", caddy)
		}
		env := generatedEnv(t, root)
		if !strings.Contains(env, "VITE_API_URL=https://p.example.com") {
			t.Fatal("expected https API URL from --api-host")
		}
	})
}

// --- config-file mode ---

func writeInitConfig(t *testing.T, dir, body string) string {
	t.Helper()
	p := filepath.Join(dir, "asunset.init.yaml")
	if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestNonInteractiveConfigFile(t *testing.T) {
	withRepoRoot(t, func(root string) {
		cfgPath := writeInitConfig(t, root, strings.Join([]string{
			"# wirebit crm client",
			"mode: tls-acme",
			"web_host: crm.wirebit.io",
			"auth_host: auth.wirebit.io",
			"api_host: api.wirebit.io",
			`acme_email: "ops@wirebit.io"  # contact`,
		}, "\n"))
		runNonInteractive(t, []string{"--config", cfgPath, "--yes"})
		env := generatedEnv(t, root)
		if !strings.Contains(env, "TLS_WEB_HOST=crm.wirebit.io") {
			t.Fatalf("config-file web_host not applied:\n%s", env)
		}
		caddy := generatedCaddyfile(t, root)
		if !strings.Contains(caddy, "email ops@wirebit.io") {
			t.Fatalf("config-file acme_email not applied / trailing comment not stripped:\n%s", caddy)
		}
	})
}

func TestFlagsOverrideConfigFile(t *testing.T) {
	withRepoRoot(t, func(root string) {
		cfgPath := writeInitConfig(t, root, "mode: plain\n")
		// Flag should win over the file's mode.
		runNonInteractive(t, []string{"--config", cfgPath, "--mode", "tailscale", "--tailscale-host", "h.ts.net", "--yes"})
		env := generatedEnv(t, root)
		if !strings.Contains(env, "ASUNSET_MODE=tailscale") {
			t.Fatalf("flag did not override config-file mode:\n%s", env)
		}
	})
}

func TestConfigFileSuppliedSecretsAreDeterministic(t *testing.T) {
	withRepoRoot(t, func(root string) {
		cfgPath := writeInitConfig(t, root, strings.Join([]string{
			"mode: plain",
			"openfga_api_key: deterministic-fga-key-123",
			"app_db_password: deterministic-app-pw-456",
		}, "\n"))
		cfg := runNonInteractive(t, []string{"--config", cfgPath, "--yes"})
		if cfg.Secrets.OpenFGAAPIKey != "deterministic-fga-key-123" {
			t.Fatalf("supplied OpenFGA key not honored: %q", cfg.Secrets.OpenFGAAPIKey)
		}
		if cfg.Secrets.AppUserPass != "deterministic-app-pw-456" {
			t.Fatalf("supplied app db password not honored: %q", cfg.Secrets.AppUserPass)
		}
		// Unsupplied secrets are still generated (non-empty).
		if cfg.Secrets.KcDbPass == "" {
			t.Fatal("unsupplied secret should have been generated")
		}
		env := generatedEnv(t, root)
		if !strings.Contains(env, "OPENFGA_API_KEY=deterministic-fga-key-123") {
			t.Fatal("deterministic secret not written to .env")
		}
	})
}

// --- consumer layout ---

func TestNonInteractiveConsumerLayoutWritesAtRoot(t *testing.T) {
	withConsumerLayout(t, func(consumerRoot, asunsetRoot string) {
		runNonInteractive(t, []string{"--mode", "plain", "--yes"})
		if _, err := os.Stat(filepath.Join(consumerRoot, ".env")); err != nil {
			t.Fatalf("expected .env at consumer root: %v", err)
		}
		if _, err := os.Stat(filepath.Join(asunsetRoot, ".env")); !os.IsNotExist(err) {
			t.Fatalf("expected NO .env inside vendor/asunset; err=%v", err)
		}
	})
}

// --- existing .env reuse / regenerate policy ---

// seedEnv writes a complete-secret .env at the layout's env path so the
// existing-.env policy paths are exercised.
func seedEnv(t *testing.T, root string) {
	t.Helper()
	cfg := buildConfig(ModePlain)
	if err := generateSecrets(&cfg); err != nil {
		t.Fatal(err)
	}
	if err := writeConfigFiles(&cfg); err != nil {
		t.Fatal(err)
	}
	if !loadExisting(t).hasAllRequiredSecrets() {
		t.Fatal("seed .env is missing required secrets")
	}
}

func loadExisting(t *testing.T) ExistingEnv {
	t.Helper()
	e, err := loadExistingEnv()
	if err != nil {
		t.Fatal(err)
	}
	return e
}

func resolveWith(t *testing.T, args []string) (Config, error) {
	t.Helper()
	opts, err := parseInitArgs(args)
	if err != nil {
		return Config{}, err
	}
	cfg, err := buildConfigFromOptions(opts)
	if err != nil {
		return Config{}, err
	}
	if err := validateConfig(&cfg); err != nil {
		return Config{}, err
	}
	return cfg, resolveSecrets(&cfg, opts, loadExisting(t))
}

func TestExistingEnvRequiresExplicitChoice(t *testing.T) {
	withRepoRoot(t, func(root string) {
		seedEnv(t, root)
		// No --reuse / --regenerate → must fail, not clobber.
		if _, err := resolveWith(t, []string{"--mode", "plain", "--yes"}); err == nil {
			t.Fatal("expected error when .env exists without an explicit secrets choice")
		}
	})
}

func TestExistingEnvReuseKeepsSecrets(t *testing.T) {
	withRepoRoot(t, func(root string) {
		seedEnv(t, root)
		before := loadExisting(t).Vars["OPENFGA_API_KEY"]
		cfg, err := resolveWith(t, []string{"--mode", "plain", "--reuse-secrets", "--yes"})
		if err != nil {
			t.Fatalf("reuse path errored: %v", err)
		}
		if cfg.Secrets.OpenFGAAPIKey != before {
			t.Fatalf("reuse changed the secret: got %q want %q", cfg.Secrets.OpenFGAAPIKey, before)
		}
		if cfg.WipeVolumes {
			t.Fatal("reuse must not wipe volumes")
		}
	})
}

func TestExistingEnvRegenerateNeedsWipe(t *testing.T) {
	withRepoRoot(t, func(root string) {
		seedEnv(t, root)
		// regenerate without --wipe-volumes → fail (data-loss acknowledgement).
		if _, err := resolveWith(t, []string{"--mode", "plain", "--regenerate-secrets", "--yes"}); err == nil {
			t.Fatal("expected error: regenerate over existing .env needs --wipe-volumes")
		}
		// regenerate WITH --wipe-volumes → succeeds, new secrets, wipe flagged.
		before := loadExisting(t).Vars["OPENFGA_API_KEY"]
		cfg, err := resolveWith(t, []string{"--mode", "plain", "--regenerate-secrets", "--wipe-volumes", "--yes"})
		if err != nil {
			t.Fatalf("regenerate+wipe errored: %v", err)
		}
		if cfg.Secrets.OpenFGAAPIKey == before {
			t.Fatal("regenerate should have produced a new secret")
		}
		if !cfg.WipeVolumes {
			t.Fatal("regenerate+wipe should set WipeVolumes")
		}
	})
}

func TestReuseSecretsWithNoExistingEnvFails(t *testing.T) {
	withRepoRoot(t, func(root string) {
		if _, err := resolveWith(t, []string{"--mode", "plain", "--reuse-secrets", "--yes"}); err == nil {
			t.Fatal("expected error: --reuse-secrets with no existing .env")
		}
	})
}

// --- validation ---

func TestValidationFailsBeforeWrite(t *testing.T) {
	cases := []struct {
		name string
		args []string
	}{
		{"missing mode", []string{"--yes"}},
		{"unknown mode", []string{"--mode", "bogus", "--yes"}},
		{"tls missing hosts", []string{"--mode", "tls-internal", "--yes"}},
		{"tls-operator missing certs", []string{"--mode", "tls-operator", "--web-host", "w", "--auth-host", "a", "--api-host", "p", "--yes"}},
		{"tls-acme bad email", []string{"--mode", "tls-acme", "--web-host", "w", "--auth-host", "a", "--api-host", "p", "--acme-email", "not-an-email", "--yes"}},
		{"tailscale missing host", []string{"--mode", "tailscale", "--yes"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			withRepoRoot(t, func(root string) {
				opts, err := parseInitArgs(tc.args)
				if err != nil {
					return // parse-level rejection is also acceptable
				}
				cfg, err := buildConfigFromOptions(opts)
				if err != nil {
					return
				}
				if err := validateConfig(&cfg); err == nil {
					t.Fatalf("expected validation error for %q", tc.name)
				}
				// And nothing was written.
				if _, err := os.Stat(filepath.Join(root, ".env")); err == nil {
					t.Fatal("validation failure must not write .env")
				}
			})
		})
	}
}

func TestConfigFileParsingErrors(t *testing.T) {
	dir := t.TempDir()
	bad := filepath.Join(dir, "bad.yaml")
	if err := os.WriteFile(bad, []byte("this line has no colon\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := loadInitConfigFile(bad); err == nil {
		t.Fatal("expected parse error on a line without a colon")
	}
	if _, err := loadInitConfigFile(filepath.Join(dir, "nope.yaml")); err == nil {
		t.Fatal("expected error for missing config file")
	}
}

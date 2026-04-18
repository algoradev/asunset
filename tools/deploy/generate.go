package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"text/template"
)

// writeConfigFiles generates .env and (for TLS modes) infra/caddy/Caddyfile
// rooted at the repo that contains this tool. Operators should run the
// wizard from the repo root.

func writeConfigFiles(cfg *Config) error {
	root, err := repoRoot()
	if err != nil {
		return err
	}

	if err := writeTemplate(cfg, envTemplate, filepath.Join(root, ".env")); err != nil {
		return fmt.Errorf("write .env: %w", err)
	}

	if cfg.IsTLS() || cfg.IsTailscale() {
		dest := filepath.Join(root, "infra", "caddy", "Caddyfile")
		if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
			return fmt.Errorf("mkdir Caddyfile dir: %w", err)
		}

		switch cfg.Mode {
		case ModeTLSInternal:
			if err := writeTemplate(cfg, caddyInternalTemplate, dest); err != nil {
				return fmt.Errorf("write Caddyfile: %w", err)
			}
		case ModeTLSOperator:
			rendered := renderSimpleTemplate(caddyOperatorTemplate, cfg)
			if err := os.WriteFile(dest, []byte(rendered), 0o644); err != nil {
				return fmt.Errorf("write Caddyfile: %w", err)
			}
		case ModeTLSAcme:
			rendered := renderSimpleTemplate(caddyAcmeTemplate, cfg)
			if err := os.WriteFile(dest, []byte(rendered), 0o644); err != nil {
				return fmt.Errorf("write Caddyfile: %w", err)
			}
		case ModeTailscale:
			// Tailscale Caddyfile has no template variables — path
			// routing is fixed, hostnames live in .env / compose only.
			if err := os.WriteFile(dest, []byte(caddyTailscaleTemplate), 0o644); err != nil {
				return fmt.Errorf("write Caddyfile: %w", err)
			}
		}
	}
	return nil
}

func writeTemplate(cfg *Config, tmplStr, dest string) error {
	t, err := template.New("t").Parse(tmplStr)
	if err != nil {
		return err
	}
	f, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer f.Close()
	return t.Execute(f, cfg)
}

// renderSimpleTemplate does {KeyName} substitution without tripping over
// Caddy's own `{...}` block syntax. Cheap and deterministic for the few
// fields we need (WebHost, AuthHost, APIHost, CertPath, KeyPath, AcmeEmail).
func renderSimpleTemplate(tmpl string, cfg *Config) string {
	subs := map[string]string{
		"{WebHost}":   cfg.WebHost,
		"{AuthHost}":  cfg.AuthHost,
		"{APIHost}":   cfg.APIHost,
		"{CertPath}":  cfg.CertPath,
		"{KeyPath}":   cfg.KeyPath,
		"{AcmeEmail}": cfg.AcmeEmail,
	}
	out := tmpl
	for k, v := range subs {
		out = strings.ReplaceAll(out, k, v)
	}
	return out
}

// repoRoot walks upward from cwd looking for compose.yml. Fails with a
// helpful message if the wizard is run from the wrong place.
func repoRoot() (string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	dir := cwd
	for {
		if _, err := os.Stat(filepath.Join(dir, "compose.yml")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", fmt.Errorf(
				"couldn't find compose.yml walking up from %s — "+
					"run this wizard from the asunset repo root",
				cwd,
			)
		}
		dir = parent
	}
}

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"text/template"
)

// writeConfigFiles generates .env and (for TLS modes) infra/caddy/Caddyfile.
// .env lands at the consumer root (== asunset root in standalone layout) so
// a single env file feeds both platform and product services in a vendored
// deployment. Caddyfile stays in the asunset tree because compose.yml mounts
// it from there.

func writeConfigFiles(cfg *Config) error {
	layout, err := detectLayout()
	if err != nil {
		return err
	}

	if err := writeTemplate(cfg, envTemplate, layout.EnvPath()); err != nil {
		return fmt.Errorf("write .env: %w", err)
	}

	// Product-declared secrets (product.yaml env.generate) join the
	// platform's in the SAME file — one root .env, one writer.
	if added, err := ensureProductSecrets(layout.EnvPath(), layout.Manifest); err != nil {
		return err
	} else if len(added) > 0 {
		fmt.Printf("generated product secret(s): %s\n", strings.Join(added, ", "))
	}

	if cfg.IsTLS() || cfg.IsTailscale() {
		dest := filepath.Join(layout.AsunsetRoot, "infra", "caddy", "Caddyfile")
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

// repoRoot locates the deployment root (containing compose.yml) via
// two strategies, in order:
//
//  1. Walk up from cwd. Matches the wizard's "run me from repo root" UX
//     and keeps tests (which chdir into a tmp dir) working.
//  2. Walk up from the binary's own path. An installed CLI lives at
//     <repo>/tools/deploy/asunset, so walking up from the executable
//     lands on the repo even when invoked from any other cwd via PATH.
func repoRoot() (string, error) {
	if cwd, err := os.Getwd(); err == nil {
		if root, ok := findComposeRoot(cwd); ok {
			return root, nil
		}
	}
	if exe, err := os.Executable(); err == nil {
		if resolved, err := filepath.EvalSymlinks(exe); err == nil {
			if root, ok := findComposeRoot(filepath.Dir(resolved)); ok {
				return root, nil
			}
		}
	}
	return "", fmt.Errorf(
		"couldn't find compose.yml — run from a directory inside the " +
			"asunset deployment, or re-run the installer to fix the symlink",
	)
}

func findComposeRoot(start string) (string, bool) {
	dir := start
	for {
		if _, err := os.Stat(filepath.Join(dir, "compose.yml")); err == nil {
			return dir, true
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", false
		}
		dir = parent
	}
}

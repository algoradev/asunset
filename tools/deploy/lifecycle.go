package main

// Lifecycle commands: thin wrappers over `docker compose` that pick the
// right `-f <overlay>` flags based on deployment mode. The operator
// doesn't type `-f compose.yml -f compose.tls.yml` anywhere — the CLI
// reads ASUNSET_MODE from the on-disk .env and builds the argv.

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

// detectMode figures out which compose overlay applies for lifecycle
// commands. Prefers the explicit ASUNSET_MODE stamp written by `init`;
// falls back to inferring from TLS_*/TAILSCALE_HOST + Caddyfile so
// deployments initialized before ASUNSET_MODE existed still work.
func detectMode() (Mode, error) {
	env, err := loadExistingEnv()
	if err != nil {
		return "", err
	}
	if !env.Present {
		return "", errors.New(".env not found — run `asunset init` first")
	}
	if m := env.Vars["ASUNSET_MODE"]; m != "" {
		return Mode(m), nil
	}
	return inferMode(env)
}

func inferMode(env ExistingEnv) (Mode, error) {
	if env.Vars["TAILSCALE_HOST"] != "" {
		return ModeTailscale, nil
	}
	if env.Vars["TLS_WEB_HOST"] == "" {
		return ModePlain, nil
	}
	root, err := repoRoot()
	if err != nil {
		return "", err
	}
	caddy, err := os.ReadFile(filepath.Join(root, "infra", "caddy", "Caddyfile"))
	if err != nil {
		return "", fmt.Errorf("couldn't read Caddyfile to infer TLS mode: %w", err)
	}
	switch {
	case bytes.Contains(caddy, []byte("local_certs")):
		return ModeTLSInternal, nil
	case bytes.Contains(caddy, []byte("tls /")):
		return ModeTLSOperator, nil
	default:
		return ModeTLSAcme, nil
	}
}

// runPassthrough runs a docker compose command and exits with its
// status. Preserves signal-exit codes so Ctrl-C on `asunset logs -f`
// returns cleanly (130) instead of looking like a CLI error.
func runPassthrough(args ...string) {
	err := run(args...)
	if err == nil {
		return
	}
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		os.Exit(exitErr.ExitCode())
	}
	die(err)
}

func composeFor(mode Mode, subcmd ...string) []string {
	cfg := &Config{Mode: mode}
	return composeArgs(cfg, subcmd...)
}

func requireMode() Mode {
	mode, err := detectMode()
	if err != nil {
		die(err)
	}
	return mode
}

func cmdUp() {
	runPassthrough(composeFor(requireMode(), "up", "-d")...)
}

func cmdDown() {
	runPassthrough(composeFor(requireMode(), "down")...)
}

func cmdRestart(extra []string) {
	args := append([]string{"restart"}, extra...)
	runPassthrough(composeFor(requireMode(), args...)...)
}

func cmdLogs(extra []string) {
	args := append([]string{"logs", "-f"}, extra...)
	runPassthrough(composeFor(requireMode(), args...)...)
}

func cmdPs() {
	runPassthrough(composeFor(requireMode(), "ps")...)
}

package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"

	"github.com/charmbracelet/huh"
)

// launch actually executes the docker compose build + up sequence, and
// (for tailscale mode) the `tailscale serve` step. Called after config
// files are on disk; the user can decline and run the commands by hand.
//
// Returns (launched, err):
//   * launched=true,  err=nil  → full deploy completed; print short success banner
//   * launched=false, err=nil  → user skipped (or docker missing); print manual Next steps
//   * launched=_,     err!=nil → something failed mid-flight; print manual Next steps + error

func runLaunch(cfg *Config) (bool, error) {
	if _, err := exec.LookPath("docker"); err != nil {
		fmt.Println()
		fmt.Println(warn.Render("! docker not found on PATH; skipping the launch step."))
		fmt.Println(muted.Render("  Install Docker Desktop (or docker-ce + compose plugin), then run the commands from the Next steps block below manually."))
		return false, nil
	}

	var confirmed bool
	summary := composeLaunchSummary(cfg)
	err := huh.NewForm(
		huh.NewGroup(
			huh.NewConfirm().
				Title("Run the deployment now?").
				Description(summary).
				Affirmative("Run it").
				Negative("Skip — I'll run it manually").
				Value(&confirmed),
		),
	).Run()
	if err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			return false, nil
		}
		return false, err
	}
	if !confirmed {
		return false, nil
	}

	// Regenerate-secrets path: Postgres volume has the old passwords,
	// so we have to wipe it before the new ones can seed.
	if cfg.WipeVolumes {
		fmt.Println()
		fmt.Println(warn.Render("Wiping existing volumes (regenerate-secrets path)..."))
		if err := run(composeArgs(cfg, "down", "-v")...); err != nil {
			return false, fmt.Errorf("docker compose down -v: %w", err)
		}
	}

	// Build phase — only the services whose image content depends on
	// env/build-args. Plain mode has nothing to rebuild here.
	if cfg.IsTLS() || cfg.IsTailscale() {
		args := composeArgs(cfg, "build", "web", "keycloak-init")
		if err := run(args...); err != nil {
			return false, fmt.Errorf("docker compose build: %w", err)
		}
	}

	// Up phase.
	if err := run(composeArgs(cfg, "up", "-d")...); err != nil {
		return false, fmt.Errorf("docker compose up: %w", err)
	}

	// Tailscale serve — only step that needs sudo. The wizard has already
	// verified tailscaled is Running + logged in, so this should succeed
	// modulo the sudo password prompt.
	if cfg.IsTailscale() {
		fmt.Println()
		fmt.Println(muted.Render("Starting `tailscale serve` (may prompt for sudo password)..."))
		if err := run("sudo", "tailscale", "serve", "--bg", "--https=443", "localhost:5173"); err != nil {
			return false, fmt.Errorf("tailscale serve: %w", err)
		}
	}

	return true, nil
}

func composeArgs(cfg *Config, subcmd ...string) []string {
	args := []string{"docker", "compose", "-f", "compose.yml"}
	switch cfg.Mode {
	case ModeTLSInternal, ModeTLSOperator, ModeTLSAcme:
		args = append(args, "-f", "compose.tls.yml")
	case ModeTailscale:
		args = append(args, "-f", "compose.tailscale.yml")
	}
	return append(args, subcmd...)
}

func composeLaunchSummary(cfg *Config) string {
	var b strings.Builder
	b.WriteString("Will run:\n")
	if cfg.WipeVolumes {
		fmt.Fprintf(&b, "  • %s  (wipes existing data)\n", strings.Join(composeArgs(cfg, "down", "-v"), " "))
	}
	if cfg.IsTLS() || cfg.IsTailscale() {
		fmt.Fprintf(&b, "  • %s\n", strings.Join(composeArgs(cfg, "build", "web", "keycloak-init"), " "))
	}
	fmt.Fprintf(&b, "  • %s\n", strings.Join(composeArgs(cfg, "up", "-d"), " "))
	if cfg.IsTailscale() {
		b.WriteString("  • sudo tailscale serve --bg --https=443 localhost:5173\n")
	}
	b.WriteString("\nBuild may take 2–3 minutes the first time. You can skip this and")
	b.WriteString("\nrun the commands yourself from the Next steps block.")
	return b.String()
}

// run inherits stdio so build output streams live and sudo's prompt
// lands on the controlling terminal. Returns the child's exit error.
func run(args ...string) error {
	fmt.Println()
	fmt.Println(muted.Render("$ " + strings.Join(args, " ")))
	cmd := exec.Command(args[0], args[1:]...)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

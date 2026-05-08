package main

import (
	"errors"
	"fmt"
	"net/mail"
	"os"
	"strings"

	"github.com/charmbracelet/huh"
	"github.com/charmbracelet/lipgloss"
)

var (
	title   = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("#7D56F4")).MarginBottom(1)
	ok      = lipgloss.NewStyle().Foreground(lipgloss.Color("42"))
	warn    = lipgloss.NewStyle().Foreground(lipgloss.Color("214"))
	errSt   = lipgloss.NewStyle().Foreground(lipgloss.Color("9")).Bold(true)
	muted   = lipgloss.NewStyle().Foreground(lipgloss.Color("241"))
	boxed   = lipgloss.NewStyle().Border(lipgloss.NormalBorder()).Padding(0, 1)
	cred    = lipgloss.NewStyle().Foreground(lipgloss.Color("226"))
)

func main() {
	if len(os.Args) < 2 {
		printHelp()
		return
	}
	switch os.Args[1] {
	case "init":
		cmdInit()
	case "up":
		cmdUp()
	case "down":
		cmdDown()
	case "restart":
		cmdRestart(os.Args[2:])
	case "logs":
		cmdLogs(os.Args[2:])
	case "ps":
		cmdPs()
	case "-h", "--help", "help":
		printHelp()
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n\n", os.Args[1])
		printHelp()
		os.Exit(2)
	}
}

func printHelp() {
	fmt.Println(title.Render("asunset — on-prem deployment control"))
	fmt.Println(muted.Render("Generates config and manages the docker compose stack for this instance.") + "\n")
	fmt.Println("Usage:")
	fmt.Println("  asunset <command> [args]")
	fmt.Println()
	fmt.Println("Commands:")
	fmt.Println("  init           Interactive setup — generate .env + Caddyfile")
	fmt.Println("  up             Start the stack (docker compose up -d)")
	fmt.Println("  down           Stop the stack (docker compose down)")
	fmt.Println("  restart [svc]  Restart one service or the whole stack")
	fmt.Println("  logs [svc]     Tail logs (all services or just one)")
	fmt.Println("  ps             Show running services")
	fmt.Println("  help           Show this help")
	fmt.Println()
	fmt.Println(muted.Render("All commands except `init` read ASUNSET_MODE from .env and pick"))
	fmt.Println(muted.Render("the right compose overlay automatically."))
	fmt.Println()
	fmt.Println(muted.Render("Consumer layout: when run from inside a vendor/asunset/ subtree,"))
	fmt.Println(muted.Render("init writes .env at the consumer root, and up/down/etc. auto-include"))
	fmt.Println(muted.Render("a sibling compose.product.yml if one exists."))
}

func cmdInit() {
	fmt.Println(title.Render("asunset · deployment wizard"))
	fmt.Println(muted.Render("Generates .env and Caddy config for this instance.") + "\n")

	cfg := newConfig()

	// If a previous wizard run left an .env on disk, default to reusing
	// its secrets. Regenerating means Postgres's existing volume has
	// old credentials while the new .env has new ones, which bricks
	// every service with "password authentication failed".
	reuseExisting := false
	existing, err := loadExistingEnv()
	if err != nil {
		die(err)
	}
	if existing.Present && existing.hasAllRequiredSecrets() {
		if !promptReuseExisting(&reuseExisting) {
			os.Exit(1)
		}
	}

	if err := runModeSelect(&cfg); err != nil {
		die(err)
	}

	// Preflight for tailscale mode: abort before the user fills in
	// anything else if the local daemon isn't ready to serve.
	if cfg.IsTailscale() && !preflightTailscaleOK() {
		os.Exit(1)
	}

	if err := runHostsForm(&cfg); err != nil {
		die(err)
	}
	if err := runCertForm(&cfg); err != nil {
		die(err)
	}
	if !confirmSummary(&cfg) {
		fmt.Println(warn.Render("\nCancelled — nothing written."))
		os.Exit(1)
	}

	fmt.Println()
	if reuseExisting {
		fmt.Print(muted.Render("Reusing existing secrets from .env... "))
		existing.fillSecrets(&cfg)
		fmt.Println(ok.Render("done"))
	} else {
		fmt.Print(muted.Render("Generating secrets... "))
		if err := generateSecrets(&cfg); err != nil {
			die(err)
		}
		fmt.Println(ok.Render("done"))
	}

	fmt.Print(muted.Render("Writing config files... "))
	if err := writeConfigFiles(&cfg); err != nil {
		die(err)
	}
	fmt.Println(ok.Render("done"))

	if !reuseExisting {
		printCredentials(&cfg)
	}

	// Regenerate path wipes volumes so Postgres init can re-seed with
	// the new passwords — otherwise pg_shadow still has the old ones
	// and every service fails auth on connect.
	cfg.WipeVolumes = !reuseExisting && existing.Present

	launched, err := runLaunch(&cfg)
	if err != nil {
		// Partial launch failure: surface the error then print the
		// manual Next steps so the operator can retry individual pieces.
		fmt.Println()
		fmt.Println(errSt.Render("launch failed: ") + err.Error())
		fmt.Println(muted.Render("Run the commands from Next steps manually to retry."))
		printNextSteps(&cfg)
		return
	}
	if launched {
		printLaunchedBanner(&cfg)
	} else {
		printNextSteps(&cfg)
	}
}

// promptReuseExisting asks whether to reuse the secrets already in .env
// (preserving on-disk DB state) or regenerate everything (which wipes
// volumes so the new passwords take effect). Returns false if the user
// aborts. The caller uses `*reuse` to choose the downstream path.
func promptReuseExisting(reuse *bool) bool {
	fmt.Println()
	fmt.Println(warn.Render("! An existing .env was found."))
	fmt.Println(muted.Render("  Regenerating secrets while a Postgres volume exists leaves the"))
	fmt.Println(muted.Render("  DB with the OLD passwords and every service fails to authenticate."))
	fmt.Println()

	var choice string
	err := huh.NewForm(
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("What should I do?").
				Options(
					huh.NewOption("Reuse existing secrets (keeps all data)", "reuse"),
					huh.NewOption("Regenerate everything (WIPES volumes — data lost)", "regenerate"),
					huh.NewOption("Cancel", "cancel"),
				).
				Value(&choice),
		),
	).Run()
	if err != nil || choice == "cancel" {
		return false
	}
	*reuse = choice == "reuse"
	return true
}

// preflightTailscaleOK checks the tailscale daemon state and, if it's
// not ready to serve, prints a specific remediation and returns false.
// Called only for tailscale deployment mode.
func preflightTailscaleOK() bool {
	s := checkTailscale()
	switch s.State {
	case TSRunning:
		return true

	case TSNotInstalled:
		fmt.Println()
		fmt.Println(errSt.Render("✗ Tailscale is not installed on this host."))
		fmt.Println(muted.Render("  Install it first, then re-run the wizard:"))
		fmt.Println("    curl -fsSL https://tailscale.com/install.sh | sh")
		fmt.Println("    sudo tailscale up")
		return false

	case TSNeedsLogin:
		fmt.Println()
		fmt.Println(errSt.Render("✗ Tailscale is installed but not logged in."))
		fmt.Println(muted.Render("  Sign in, then re-run the wizard:"))
		fmt.Println("    sudo tailscale up")
		if s.AuthURL != "" {
			fmt.Println(muted.Render("  Or open this auth URL directly:"))
			fmt.Println("    " + s.AuthURL)
		}
		return false

	case TSStopped:
		fmt.Println()
		fmt.Println(errSt.Render("✗ Tailscale is installed but stopped."))
		fmt.Println(muted.Render("  Start it, then re-run the wizard:"))
		fmt.Println("    sudo tailscale up")
		return false

	default:
		fmt.Println()
		fmt.Println(errSt.Render("✗ Couldn't determine Tailscale state."))
		if s.RawErr != "" {
			fmt.Println(muted.Render("  " + s.RawErr))
		}
		fmt.Println(muted.Render("  Verify with: tailscale status --json"))
		return false
	}
}

func die(err error) {
	if errors.Is(err, huh.ErrUserAborted) {
		fmt.Println(warn.Render("\nCancelled."))
		os.Exit(1)
	}
	fmt.Println(errSt.Render("error: ") + err.Error())
	os.Exit(1)
}

// --- form steps ---

func runModeSelect(cfg *Config) error {
	var mode string
	err := huh.NewForm(
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("Deployment mode").
				Description("Where will end users reach this instance from?").
				Options(
					huh.NewOption("Local dev (HTTP on localhost)", "plain"),
					huh.NewOption("TLS, Caddy's internal CA (dev/staging)", "tls-internal"),
					huh.NewOption("TLS, your own cert files (typical on-prem)", "tls-operator"),
					huh.NewOption("TLS, Let's Encrypt (public internet)", "tls-acme"),
					huh.NewOption("Tailscale (MagicDNS + serve; tailnet-only)", "tailscale"),
				).
				Value(&mode),
		),
	).Run()
	if err != nil {
		return err
	}
	cfg.Mode = Mode(mode)
	return nil
}

func runHostsForm(cfg *Config) error {
	if cfg.IsTailscale() {
		// `tailscale serve` publishes on THIS machine's Self.DNSName
		// regardless of what the user types. Anything else breaks
		// silently at browser time (the browser can't resolve a name
		// that doesn't exist on the tailnet). So: we detect the real
		// FQDN, pin it, and refuse manual overrides that don't match.
		detected, found := detectTailscaleHost()
		if !found {
			// Preflight should catch this, but be defensive.
			return errors.New("couldn't detect the host's Tailscale FQDN; preflight should have caught this")
		}
		cfg.TailscaleHost = detected

		var confirmed bool
		err := huh.NewForm(
			huh.NewGroup(
				huh.NewConfirm().
					Title("Confirm Tailscale hostname").
					Description(
						"tailscale serve publishes on your machine's actual\n"+
							"tailnet FQDN — different names won't resolve.\n\n"+
							ok.Render("Detected: "+detected)+"\n\n"+
							muted.Render("If you want a different hostname (e.g. \"asunset\"),\n"+
								"rename the machine in the Tailscale admin console first,\n"+
								"then re-run this wizard."),
					).
					Affirmative("Use this hostname").
					Negative("Cancel").
					Value(&confirmed),
			).Title("Tailscale hostname"),
		).Run()
		if err != nil || !confirmed {
			return errors.New("cancelled")
		}
		return nil
	}
	if !cfg.IsTLS() {
		return nil
	}
	return huh.NewForm(
		huh.NewGroup(
			huh.NewInput().
				Title("Web UI hostname").
				Description("The URL end users open in their browser.").
				Placeholder("asunset.example.com").
				Value(&cfg.WebHost).
				Validate(notEmpty),
			huh.NewInput().
				Title("Keycloak (auth) hostname").
				Placeholder("auth.asunset.example.com").
				Value(&cfg.AuthHost).
				Validate(notEmpty),
			huh.NewInput().
				Title("API hostname").
				Placeholder("api.asunset.example.com").
				Value(&cfg.APIHost).
				Validate(notEmpty),
		).Title("Hostnames"),
	).Run()
}

func runCertForm(cfg *Config) error {
	switch cfg.Mode {
	case ModeTLSOperator:
		return huh.NewForm(
			huh.NewGroup(
				huh.NewInput().
					Title("TLS fullchain cert path (on host)").
					Description("Must exist before `docker compose up`. Mounted into Caddy.").
					Placeholder("/etc/ssl/asunset/fullchain.pem").
					Value(&cfg.CertPath).
					Validate(notEmpty),
				huh.NewInput().
					Title("TLS private key path (on host)").
					Placeholder("/etc/ssl/asunset/privkey.pem").
					Value(&cfg.KeyPath).
					Validate(notEmpty),
			).Title("Operator certificates"),
		).Run()
	case ModeTLSAcme:
		return huh.NewForm(
			huh.NewGroup(
				huh.NewInput().
					Title("Email for ACME / Let's Encrypt").
					Description("Let's Encrypt sends renewal-failure notices here.").
					Placeholder("ops@example.com").
					Value(&cfg.AcmeEmail).
					Validate(validEmail),
			).Title("Let's Encrypt"),
		).Run()
	}
	return nil
}

func confirmSummary(cfg *Config) bool {
	var b strings.Builder
	fmt.Fprintln(&b, title.Render("Summary"))
	fmt.Fprintf(&b, "  Mode:  %s\n", cfg.Mode)
	switch {
	case cfg.IsTLS():
		fmt.Fprintf(&b, "  Web:   https://%s\n", cfg.WebHost)
		fmt.Fprintf(&b, "  Auth:  https://%s\n", cfg.AuthHost)
		fmt.Fprintf(&b, "  API:   https://%s\n", cfg.APIHost)
	case cfg.IsTailscale():
		fmt.Fprintf(&b, "  Host:  https://%s\n", cfg.TailscaleHost)
		fmt.Fprintf(&b, "  Auth:  https://%s/auth\n", cfg.TailscaleHost)
		fmt.Fprintf(&b, "  API:   https://%s/api\n", cfg.TailscaleHost)
	default:
		fmt.Fprintln(&b, "  Web:   http://localhost:3000")
		fmt.Fprintln(&b, "  Auth:  http://localhost:8080")
		fmt.Fprintln(&b, "  API:   http://localhost:8000")
	}
	switch cfg.Mode {
	case ModeTLSOperator:
		fmt.Fprintf(&b, "  Cert:  %s\n", cfg.CertPath)
		fmt.Fprintf(&b, "  Key:   %s\n", cfg.KeyPath)
	case ModeTLSAcme:
		fmt.Fprintf(&b, "  ACME:  %s\n", cfg.AcmeEmail)
	}
	fmt.Fprintln(&b, muted.Render("  (strong random secrets will be generated for everything else)"))
	fmt.Println(boxed.Render(b.String()))

	var confirmed bool
	err := huh.NewForm(
		huh.NewGroup(
			huh.NewConfirm().
				Title("Generate config with these settings?").
				Affirmative("Generate").
				Negative("Cancel").
				Value(&confirmed),
		),
	).Run()
	if err != nil {
		return false
	}
	return confirmed
}

// --- validators ---

func notEmpty(s string) error {
	if strings.TrimSpace(s) == "" {
		return errors.New("required")
	}
	return nil
}

func validEmail(s string) error {
	if _, err := mail.ParseAddress(s); err != nil {
		return errors.New("not a valid email")
	}
	return nil
}

// --- post-generation output ---

func printCredentials(cfg *Config) {
	var b strings.Builder
	fmt.Fprintln(&b, title.Render("Generated credentials — save these NOW"))
	fmt.Fprintln(&b, warn.Render("  These are in .env (gitignored) but copy them somewhere safe."))
	fmt.Fprintln(&b, warn.Render("  Re-running the wizard generates new values; old ones are lost."))
	fmt.Fprintln(&b)
	s := cfg.Secrets
	writeCred(&b, "Keycloak admin user", s.KeycloakAdmin)
	writeCred(&b, "Keycloak admin password", s.KeycloakAdminPass)
	writeCred(&b, "API client secret", s.KeycloakAPISecret)
	writeCred(&b, "OpenFGA API key", s.OpenFGAAPIKey)
	writeCred(&b, "Postgres superuser password", s.PostgresSuperPass)
	writeCred(&b, "App DB owner password", s.AppOwnerPass)
	writeCred(&b, "App DB user password", s.AppUserPass)
	writeCred(&b, "Keycloak DB password", s.KcDbPass)
	writeCred(&b, "OpenFGA DB password", s.FgaDbPass)
	fmt.Println()
	fmt.Println(boxed.Render(b.String()))
}

func writeCred(b *strings.Builder, label, value string) {
	fmt.Fprintf(b, "  %-32s %s\n", label+":", cred.Render(value))
}

// printLaunchedBanner is the post-success output. Just the URL to open
// and the management commands relevant to the chosen mode — no manual
// rerun-the-commands block.
func printLaunchedBanner(cfg *Config) {
	fmt.Println()
	fmt.Println(ok.Render("✓ Deployment running."))
	fmt.Println()
	switch {
	case cfg.IsTLS():
		fmt.Println(muted.Render("  URL:"))
		fmt.Printf("    https://%s/\n", cfg.WebHost)
	case cfg.IsTailscale():
		fmt.Println(muted.Render("  URL (any device on your tailnet):"))
		fmt.Printf("    https://%s/\n", cfg.TailscaleHost)
		fmt.Println()
		fmt.Println(muted.Render("  Manage Tailscale serve:"))
		fmt.Println("    tailscale serve status")
		fmt.Println("    sudo tailscale serve --https=443 off")
	default:
		fmt.Println(muted.Render("  URL:"))
		fmt.Println("    http://localhost:3000/")
	}
	fmt.Println()
	fmt.Println(muted.Render("  Stack control:"))
	stop := strings.Join(composeArgs(cfg, "stop"), " ")
	logs := strings.Join(composeArgs(cfg, "logs", "-f"), " ")
	fmt.Println("    " + stop)
	fmt.Println("    " + logs)
}

func printNextSteps(cfg *Config) {
	fmt.Println()
	fmt.Println(title.Render("Next steps"))
	build := strings.Join(composeArgs(cfg, "build", "web", "keycloak-init"), " ")
	up := strings.Join(composeArgs(cfg, "up", "-d"), " ")
	switch {
	case cfg.IsTLS():
		fmt.Println(muted.Render("  Add hostnames to DNS (or /etc/hosts for local dev):"))
		fmt.Printf("    127.0.0.1 %s %s %s\n\n", cfg.WebHost, cfg.AuthHost, cfg.APIHost)
		fmt.Println(muted.Render("  Build + launch:"))
		fmt.Println("    " + build)
		fmt.Println("    " + up)
		fmt.Printf("\n  Open https://%s/\n", cfg.WebHost)

	case cfg.IsTailscale():
		fmt.Println(muted.Render("  Prerequisites (one-time on this host):"))
		fmt.Println("    curl -fsSL https://tailscale.com/install.sh | sh")
		fmt.Println("    sudo tailscale up")
		fmt.Printf("    sudo tailscale cert %s\n\n", cfg.TailscaleHost)
		fmt.Println(muted.Render("  Build + launch the stack:"))
		fmt.Println("    " + build)
		fmt.Println("    " + up)
		fmt.Println()
		fmt.Println(muted.Render("  Expose on :443 (Tailscale terminates TLS):"))
		fmt.Println("    sudo tailscale serve --bg --https=443 localhost:5173")
		fmt.Printf("\n  Any device on your tailnet: https://%s/\n", cfg.TailscaleHost)

	default:
		fmt.Println(muted.Render("  Launch:"))
		fmt.Println("    " + up)
		fmt.Println("\n  Open http://localhost:3000/")
	}
	if layout, err := detectLayout(); err == nil && layout.Vendored {
		fmt.Println()
		fmt.Println(muted.Render("  (Consumer layout detected — compose.product.yml is auto-included.)"))
	}
}

package main

// Non-interactive `asunset init` — config-file + flag driven generation for
// reproducible deployments (CodePipeline, Lightsail user-data, CI).
//
// The interactive wizard (cmdInitInteractive) stays the default when `init`
// is run with no args. Any args switch to this path. The two share the same
// downstream: a populated Config flows through validate → secrets → write →
// (optional) launch, exactly as the wizard does.
//
// Config-file format is a flat `key: value` subset of YAML (scalars only —
// every field the wizard collects is a scalar, so no nesting/lists are
// needed). Dependency-free on purpose, matching the tool's minimal-dep ethos
// and existing.go's hand-rolled .env reader.

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"strings"
)

// initOptions is the fully-resolved, post-merge intent for a non-interactive
// run: config-file values overlaid by explicitly-set flags (flags win).
type initOptions struct {
	configPath string

	mode          string
	webHost       string
	authHost      string
	apiHost       string
	certPath      string
	keyPath       string
	acmeEmail     string
	tailscaleHost string

	// Secrets policy when an .env already exists. Exactly one of these is
	// required in that case; both unset → fail (no silent clobber).
	reuseSecrets      bool
	regenerateSecrets bool
	wipeVolumes       bool

	// Launch policy. Default in non-interactive mode is write-only (no
	// docker invocation) — pipelines want deterministic file generation,
	// not an interactive container launch.
	launch       bool
	yes          bool
	printSecrets bool

	// suppliedSecrets are operator-provided secret values (from the config
	// file and/or environment) keyed by canonical .env name. Any not
	// supplied are crypto-generated, so a partial set is fine.
	suppliedSecrets map[string]string
}

// canonical .env names for the nine secrets, mapped to their Config field
// setter. Used for both config-file keys and environment-variable lookup.
var secretEnvNames = []string{
	"KEYCLOAK_ADMIN",
	"KEYCLOAK_ADMIN_PASSWORD",
	"KEYCLOAK_API_CLIENT_SECRET",
	"OPENFGA_API_KEY",
	"POSTGRES_SUPERUSER_PASSWORD",
	"APP_DB_OWNER_PASSWORD",
	"APP_DB_PASSWORD",
	"KC_DB_PASSWORD",
	"FGA_DB_PASSWORD",
	"SESSION_TOKEN_PRIVATE_KEY_B64",
}

// configKeyToEnv maps flat config-file keys (snake_case) to canonical .env
// secret names. Lets a single `asunset.init.yaml` carry deterministic secrets
// for reproducible provisioning.
var configKeyToEnv = map[string]string{
	"keycloak_admin":              "KEYCLOAK_ADMIN",
	"keycloak_admin_password":     "KEYCLOAK_ADMIN_PASSWORD",
	"keycloak_api_client_secret":  "KEYCLOAK_API_CLIENT_SECRET",
	"openfga_api_key":             "OPENFGA_API_KEY",
	"postgres_superuser_password": "POSTGRES_SUPERUSER_PASSWORD",
	"app_db_owner_password":       "APP_DB_OWNER_PASSWORD",
	"app_db_password":             "APP_DB_PASSWORD",
	"kc_db_password":              "KC_DB_PASSWORD",
	"fga_db_password":             "FGA_DB_PASSWORD",
	"session_token_private_key_b64": "SESSION_TOKEN_PRIVATE_KEY_B64",
}

// cmdInit dispatches between the interactive wizard (no args) and the
// non-interactive path (any args, incl. -h/--help for init).
func cmdInit(args []string) {
	if len(args) == 0 {
		cmdInitInteractive()
		return
	}
	switch args[0] {
	case "-h", "--help", "help":
		printInitHelp()
		return
	}
	if err := cmdInitNonInteractive(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return // flag already printed usage
		}
		fmt.Fprintln(os.Stderr, errSt.Render("error: ")+err.Error())
		os.Exit(1)
	}
}

func cmdInitNonInteractive(args []string) error {
	opts, err := parseInitArgs(args)
	if err != nil {
		return err
	}
	if !opts.yes {
		return fmt.Errorf("non-interactive init requires --yes to confirm unattended generation")
	}

	cfg, err := buildConfigFromOptions(opts)
	if err != nil {
		return err
	}
	// Validate BEFORE touching disk so an invalid combination fails clean.
	if err := validateConfig(&cfg); err != nil {
		return err
	}

	existing, err := loadExistingEnv()
	if err != nil {
		return err
	}
	if err := resolveSecrets(&cfg, opts, existing); err != nil {
		return err
	}

	if err := writeConfigFiles(&cfg); err != nil {
		return err
	}

	fmt.Println(ok.Render("✓") + " wrote config for mode " + muted.Render(string(cfg.Mode)))
	if opts.printSecrets && !opts.reuseSecrets {
		printCredentials(&cfg)
	} else {
		fmt.Println(muted.Render("  secrets written to .env (not echoed; pass --print-secrets to display)"))
	}

	if opts.launch {
		if err := runLaunchNonInteractive(&cfg); err != nil {
			return fmt.Errorf("launch: %w", err)
		}
		fmt.Println(ok.Render("✓ deployment running."))
		return nil
	}
	printNextSteps(&cfg)
	return nil
}

// parseInitArgs parses flags, then overlays a config file (flags win over the
// file). Returns the resolved options.
func parseInitArgs(args []string) (initOptions, error) {
	fs := flag.NewFlagSet("init", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	fs.Usage = func() { printInitHelp() }

	var (
		configPath        = fs.String("config", "", "path to a flat key:value config file")
		mode              = fs.String("mode", "", "deployment mode: plain|tls-internal|tls-operator|tls-acme|tailscale")
		webHost           = fs.String("web-host", "", "web UI hostname (TLS modes)")
		authHost          = fs.String("auth-host", "", "Keycloak hostname (TLS modes)")
		apiHost           = fs.String("api-host", "", "API hostname (TLS modes)")
		certPath          = fs.String("cert-path", "", "TLS fullchain cert path on host (tls-operator)")
		keyPath           = fs.String("key-path", "", "TLS private key path on host (tls-operator)")
		acmeEmail         = fs.String("acme-email", "", "ACME/Let's Encrypt contact email (tls-acme)")
		tailscaleHost     = fs.String("tailscale-host", "", "tailnet FQDN (tailscale mode; asserted, not auto-detected)")
		reuseSecrets      = fs.Bool("reuse-secrets", false, "reuse secrets from an existing .env (keeps DB volumes)")
		regenerateSecrets = fs.Bool("regenerate-secrets", false, "regenerate secrets over an existing .env (requires --wipe-volumes)")
		wipeVolumes       = fs.Bool("wipe-volumes", false, "acknowledge data loss when regenerating over an existing deployment")
		launch            = fs.Bool("launch", false, "run docker compose after writing config (default: write only)")
		yes               = fs.Bool("yes", false, "confirm unattended generation (required)")
		printSecrets      = fs.Bool("print-secrets", false, "echo generated secrets to stdout (off by default; pipeline logs)")
	)
	// Short aliases.
	fs.StringVar(configPath, "c", "", "alias for --config")
	fs.BoolVar(yes, "y", false, "alias for --yes")

	if err := fs.Parse(args); err != nil {
		return initOptions{}, err
	}

	set := map[string]bool{}
	fs.Visit(func(f *flag.Flag) { set[f.Name] = true })

	// Resolve --config from flag (either long or short alias).
	cfgPath := *configPath
	fileVals := map[string]string{}
	if cfgPath != "" {
		v, err := loadInitConfigFile(cfgPath)
		if err != nil {
			return initOptions{}, err
		}
		fileVals = v
	}

	// pick: explicit flag wins; else config-file value; else flag default ("").
	pick := func(longName, fileKey, flagVal string) string {
		if set[longName] {
			return flagVal
		}
		if v, ok := fileVals[fileKey]; ok {
			return v
		}
		return flagVal
	}
	pickBool := func(longName, fileKey string, flagVal bool) bool {
		if set[longName] {
			return flagVal
		}
		if v, ok := fileVals[fileKey]; ok {
			return parseBool(v)
		}
		return flagVal
	}

	opts := initOptions{
		configPath:        cfgPath,
		mode:              pick("mode", "mode", *mode),
		webHost:           pick("web-host", "web_host", *webHost),
		authHost:          pick("auth-host", "auth_host", *authHost),
		apiHost:           pick("api-host", "api_host", *apiHost),
		certPath:          pick("cert-path", "cert_path", *certPath),
		keyPath:           pick("key-path", "key_path", *keyPath),
		acmeEmail:         pick("acme-email", "acme_email", *acmeEmail),
		tailscaleHost:     pick("tailscale-host", "tailscale_host", *tailscaleHost),
		reuseSecrets:      pickBool("reuse-secrets", "reuse_secrets", *reuseSecrets),
		regenerateSecrets: pickBool("regenerate-secrets", "regenerate_secrets", *regenerateSecrets),
		wipeVolumes:       pickBool("wipe-volumes", "wipe_volumes", *wipeVolumes),
		launch:            pickBool("launch", "launch", *launch),
		yes:               *yes || set["y"],
		printSecrets:      pickBool("print-secrets", "print_secrets", *printSecrets),
	}

	// Collect operator-supplied secrets: config-file key wins over env var.
	opts.suppliedSecrets = map[string]string{}
	for _, envName := range secretEnvNames {
		if v := os.Getenv(envName); v != "" {
			opts.suppliedSecrets[envName] = v
		}
	}
	for fileKey, envName := range configKeyToEnv {
		if v, ok := fileVals[fileKey]; ok && v != "" {
			opts.suppliedSecrets[envName] = v
		}
	}

	return opts, nil
}

// buildConfigFromOptions maps resolved options onto a Config. Secrets are
// resolved separately (resolveSecrets) once the existing-.env state is known.
func buildConfigFromOptions(opts initOptions) (Config, error) {
	// Deliberately a bare Config, NOT newConfig() — the wizard seeds
	// asunset.local host placeholders for interactive editing, but an
	// unattended run must state its hostnames explicitly (asunset.local
	// would silently produce a broken real deployment). Missing TLS hosts
	// therefore fail validation rather than defaulting.
	return Config{
		Mode:          Mode(opts.mode),
		WebHost:       opts.webHost,
		AuthHost:      opts.authHost,
		APIHost:       opts.apiHost,
		CertPath:      opts.certPath,
		KeyPath:       opts.keyPath,
		AcmeEmail:     opts.acmeEmail,
		TailscaleHost: opts.tailscaleHost,
	}, nil
}

// validateConfig enforces mode validity and per-mode required fields, reusing
// the same checks the interactive validators apply. Runs before any write.
func validateConfig(cfg *Config) error {
	switch cfg.Mode {
	case ModePlain:
		// no host/cert inputs needed
	case ModeTLSInternal, ModeTLSOperator, ModeTLSAcme:
		for _, f := range []struct{ name, val string }{
			{"web-host", cfg.WebHost},
			{"auth-host", cfg.AuthHost},
			{"api-host", cfg.APIHost},
		} {
			if notEmpty(f.val) != nil {
				return fmt.Errorf("mode %s requires --%s", cfg.Mode, f.name)
			}
		}
		if cfg.Mode == ModeTLSOperator {
			if notEmpty(cfg.CertPath) != nil || notEmpty(cfg.KeyPath) != nil {
				return fmt.Errorf("mode tls-operator requires --cert-path and --key-path")
			}
		}
		if cfg.Mode == ModeTLSAcme {
			if validEmail(cfg.AcmeEmail) != nil {
				return fmt.Errorf("mode tls-acme requires a valid --acme-email")
			}
		}
	case ModeTailscale:
		if notEmpty(cfg.TailscaleHost) != nil {
			return fmt.Errorf("mode tailscale requires --tailscale-host (asserted, not auto-detected in non-interactive mode)")
		}
	case "":
		return fmt.Errorf("--mode is required (one of plain|tls-internal|tls-operator|tls-acme|tailscale)")
	default:
		return fmt.Errorf("unknown mode %q (want plain|tls-internal|tls-operator|tls-acme|tailscale)", cfg.Mode)
	}
	return nil
}

// resolveSecrets implements the explicit existing-.env policy for unattended
// runs: never silently clobber, never leave a half-populated set.
func resolveSecrets(cfg *Config, opts initOptions, existing ExistingEnv) error {
	usableExisting := existing.Present && existing.hasAllRequiredSecrets()

	if opts.reuseSecrets && opts.regenerateSecrets {
		return fmt.Errorf("--reuse-secrets and --regenerate-secrets are mutually exclusive")
	}

	if usableExisting {
		switch {
		case opts.reuseSecrets:
			existing.fillSecrets(cfg)
			cfg.WipeVolumes = false
			return nil
		case opts.regenerateSecrets:
			if !opts.wipeVolumes {
				return fmt.Errorf("regenerating secrets over an existing .env needs --wipe-volumes to acknowledge data loss (the old Postgres volume holds the old passwords)")
			}
			if err := freshSecrets(cfg, opts); err != nil {
				return err
			}
			cfg.WipeVolumes = true
			return nil
		default:
			return fmt.Errorf("an existing .env was found; pass --reuse-secrets (keep data) or --regenerate-secrets --wipe-volumes (destroy data)")
		}
	}

	// No usable existing .env. reuse-secrets has nothing to reuse.
	if opts.reuseSecrets {
		return fmt.Errorf("--reuse-secrets given but no existing .env with a complete secret set was found")
	}
	if err := freshSecrets(cfg, opts); err != nil {
		return err
	}
	cfg.WipeVolumes = false
	return nil
}

// freshSecrets generates a full secret set, then overrides with any
// operator-supplied values (deterministic provisioning). Generating first
// guarantees completeness even when only a subset is supplied.
func freshSecrets(cfg *Config, opts initOptions) error {
	if err := generateSecrets(cfg); err != nil {
		return err
	}
	for envName, val := range opts.suppliedSecrets {
		applySecret(cfg, envName, val)
	}
	return nil
}

func applySecret(cfg *Config, envName, val string) {
	switch envName {
	case "KEYCLOAK_ADMIN":
		cfg.Secrets.KeycloakAdmin = val
	case "KEYCLOAK_ADMIN_PASSWORD":
		cfg.Secrets.KeycloakAdminPass = val
	case "KEYCLOAK_API_CLIENT_SECRET":
		cfg.Secrets.KeycloakAPISecret = val
	case "OPENFGA_API_KEY":
		cfg.Secrets.OpenFGAAPIKey = val
	case "POSTGRES_SUPERUSER_PASSWORD":
		cfg.Secrets.PostgresSuperPass = val
	case "APP_DB_OWNER_PASSWORD":
		cfg.Secrets.AppOwnerPass = val
	case "APP_DB_PASSWORD":
		cfg.Secrets.AppUserPass = val
	case "KC_DB_PASSWORD":
		cfg.Secrets.KcDbPass = val
	case "FGA_DB_PASSWORD":
		cfg.Secrets.FgaDbPass = val
	case "SESSION_TOKEN_PRIVATE_KEY_B64":
		cfg.Secrets.SessionTokenKeyB64 = val
	}
}

// loadInitConfigFile reads a flat key:value config file (scalar YAML subset).
// Blank lines and `#` comments are skipped; values may be optionally quoted.
func loadInitConfigFile(path string) (map[string]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config %s: %w", path, err)
	}
	out := map[string]string{}
	for i, raw := range strings.Split(string(data), "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, val, ok := strings.Cut(line, ":")
		if !ok {
			return nil, fmt.Errorf("%s:%d: expected `key: value`, got %q", path, i+1, line)
		}
		out[strings.TrimSpace(key)] = parseScalar(strings.TrimSpace(val))
	}
	return out, nil
}

// parseScalar resolves a config value: a quoted string yields its inner
// content (trailing inline comment ignored); an unquoted value is taken up to
// a ` #` inline comment.
func parseScalar(val string) string {
	if val == "" {
		return ""
	}
	if q := val[0]; q == '"' || q == '\'' {
		if j := strings.IndexByte(val[1:], q); j >= 0 {
			return val[1 : 1+j]
		}
		return val[1:] // unterminated quote — best effort
	}
	if h := strings.Index(val, " #"); h >= 0 {
		val = val[:h]
	}
	return strings.TrimSpace(val)
}

func parseBool(s string) bool {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "true", "yes", "y", "1", "on":
		return true
	}
	return false
}

// runLaunchNonInteractive runs the compose sequence without the huh confirm —
// the unattended analogue of runLaunch's post-confirmation steps.
func runLaunchNonInteractive(cfg *Config) error {
	if cfg.WipeVolumes {
		if err := run(composeArgs(cfg, "down", "-v")...); err != nil {
			return fmt.Errorf("docker compose down -v: %w", err)
		}
	}
	if cfg.IsTLS() || cfg.IsTailscale() {
		if err := run(composeArgs(cfg, "build", "web", "keycloak-init")...); err != nil {
			return fmt.Errorf("docker compose build: %w", err)
		}
	}
	if err := run(composeArgs(cfg, "up", "-d")...); err != nil {
		return fmt.Errorf("docker compose up: %w", err)
	}
	if cfg.IsTailscale() {
		if err := run("sudo", "tailscale", "serve", "--bg", "--https=443", "localhost:5173"); err != nil {
			return fmt.Errorf("tailscale serve: %w", err)
		}
	}
	return nil
}

func printInitHelp() {
	fmt.Println(title.Render("asunset init — generate .env + Caddy config"))
	fmt.Println(muted.Render("Run with no args for the interactive wizard, or pass flags/--config for") )
	fmt.Println(muted.Render("unattended generation (CodePipeline, Lightsail user-data, CI).") + "\n")
	fmt.Println("Non-interactive usage:")
	fmt.Println("  asunset init --config deploy/asunset.init.yaml --yes")
	fmt.Println("  asunset init --mode tailscale --tailscale-host host.tailnet.ts.net --yes")
	fmt.Println("  asunset init --mode tls-operator --web-host w --auth-host a --api-host p \\")
	fmt.Println("       --cert-path /c/full.pem --key-path /c/key.pem --yes")
	fmt.Println()
	fmt.Println("Flags:")
	fmt.Println("  --config, -c        flat key:value config file (flags override file values)")
	fmt.Println("  --yes, -y           confirm unattended generation (REQUIRED)")
	fmt.Println("  --mode              plain | tls-internal | tls-operator | tls-acme | tailscale")
	fmt.Println("  --web-host / --auth-host / --api-host   hostnames (TLS modes)")
	fmt.Println("  --cert-path / --key-path                cert files (tls-operator)")
	fmt.Println("  --acme-email                            ACME contact (tls-acme)")
	fmt.Println("  --tailscale-host                        tailnet FQDN (tailscale; asserted)")
	fmt.Println("  --reuse-secrets                         keep an existing .env's secrets + volumes")
	fmt.Println("  --regenerate-secrets --wipe-volumes     replace secrets, destroy existing data")
	fmt.Println("  --launch                                run docker compose after writing (default: write only)")
	fmt.Println("  --print-secrets                         echo generated secrets (off by default)")
	fmt.Println()
	fmt.Println(muted.Render("  Secrets may be supplied for deterministic provisioning via config-file"))
	fmt.Println(muted.Render("  keys or the canonical env vars (KEYCLOAK_ADMIN_PASSWORD, etc.); any not"))
	fmt.Println(muted.Render("  supplied are crypto-generated. Existing .env requires an explicit"))
	fmt.Println(muted.Render("  --reuse-secrets or --regenerate-secrets --wipe-volumes."))
}

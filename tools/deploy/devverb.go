package main

// `asunset dev` and `asunset upgrade` — the two verbs report 95 added
// to the operator surface (dev · init · up · doctor · upgrade).
//
// dev: the zero-prompt INTEGRATION environment — the tailscale
// (path-multiplexed caddy) topology on http://127.0.0.1:5173 with no
// tailnet, every secret generated, product one-shots sequenced, both
// doctors run. Explicitly NOT a replacement for a product's own
// unauthenticated inner loop (relay guard 6).
//
// upgrade: the vendor-bump runbook as one verb — and it NEVER touches
// the consumer's git (ruled boundary): the subtree pull is the
// operator's/CI's; upgrade rebuilds what bakes, force-recreates
// keycloak-init (the single most common vendor-bump mistake), rolls the
// stack, and gates on both doctors with honest partial-state reporting.

import (
	"fmt"
	"os"
	"strings"
)

const devEnvBlock = `
# ---- dev loopback (asunset dev) ----
# Same path-multiplexed topology as tailscale mode, served on loopback.
# These two overrides are what keep TAILSCALE_HOST empty from deriving
# broken https:// URLs in the overlay.
WEB_BASE_URL=http://127.0.0.1:5173
KC_BASE_URL=http://127.0.0.1:5173
`

func cmdDev() {
	env, err := loadExistingEnv()
	if err != nil {
		die(err)
	}
	if env.Present {
		// Never quietly convert a configured deployment into dev.
		if env.Vars["WEB_BASE_URL"] == "" && env.Vars["ASUNSET_MODE"] != "" &&
			env.Vars["ASUNSET_MODE"] != string(ModePlain) {
			die(fmt.Errorf(".env exists and is a configured %s deployment — refusing to dev over it "+
				"(use `asunset up`, or remove .env to start a fresh dev instance)",
				env.Vars["ASUNSET_MODE"]))
		}
		fmt.Println("dev: reusing existing dev .env")
	} else {
		fmt.Println("dev: generating loopback config (no prompts — dev never asks)")
		cfg := Config{Mode: ModeTailscale, DevLoopback: true}
		if err := generateSecrets(&cfg); err != nil {
			die(err)
		}
		if err := writeConfigFiles(&cfg); err != nil {
			die(err)
		}
		layout, err := detectLayout()
		if err != nil {
			die(err)
		}
		if err := appendOnce(layout.EnvPath(), "WEB_BASE_URL=", devEnvBlock); err != nil {
			die(err)
		}
	}

	// The rest is exactly `asunset up` — same muscle, zero prompts.
	cmdUp()
	fmt.Printf("\ndev ready → %s\n", devLoopbackOrigin)
}

// appendOnce appends block to path unless marker already occurs.
func appendOnce(path, marker, block string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if strings.Contains(string(data), marker) {
		return nil
	}
	f, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = f.WriteString(block)
	return err
}

func cmdUpgrade() {
	mode := requireMode()
	layout, err := detectLayout()
	if err != nil {
		die(err)
	}

	fmt.Println("upgrade — note: this verb never touches your git history; the vendor")
	fmt.Println("subtree is whatever you (or CI) last pulled. Dirty-tree pull recipe:")
	fmt.Println("consuming-asunset.md §8.")

	step := func(n int, what string, args []string) {
		fmt.Printf("\n[%d/4] %s\n", n, what)
		if err := run(args...); err != nil {
			fmt.Fprintf(os.Stderr, "\nPARTIAL STATE: upgrade stopped at step %d (%s).\n"+
				"Steps 1–%d completed; the stack may be mid-roll. Fix and re-run "+
				"`asunset upgrade` — every step is idempotent.\n", n, what, n-1)
			os.Exit(1)
		}
	}

	step(1, "rebuild what bakes", composeFor(mode, "build"))
	// The single most common vendor-bump mistake, automated: keycloak-init
	// is a one-shot; env/script changes only apply on a force-recreate.
	step(2, "force-recreate keycloak-init", composeFor(mode, "up", "-d", "--force-recreate", "keycloak-init"))
	step(3, "roll the stack", composeFor(mode, "up", "-d"))

	if m := layout.Manifest; m != nil && m.Doctor != "" {
		step(4, "product doctor ("+m.Doctor+")", composeFor(mode, "run", "--rm", m.Doctor))
	} else {
		fmt.Println("\n[4/4] product doctor: none declared (no product.yaml)")
	}

	// Platform doctor as the final gate — summary form, fail-honest.
	env, err := loadExistingEnv()
	if err != nil {
		die(err)
	}
	results := doctorStaticChecks(env.Vars)
	results = append(results, doctorLiveChecks(env.Vars)...)
	fails := 0
	for _, r := range results {
		if r.Status == statusFail {
			fails++
			fmt.Printf("  ✗ %-20s %s\n", r.Name, r.Detail)
		}
	}
	if fails > 0 {
		fmt.Fprintf(os.Stderr, "\nPARTIAL STATE: upgrade applied but the platform doctor reports %d failure(s) — not ready. Full detail: asunset doctor\n", fails)
		os.Exit(1)
	}
	fmt.Println("\nupgrade complete — both doctors clean (warns tolerated; see asunset doctor).")
}

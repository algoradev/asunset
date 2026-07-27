package main

// Layout detection.
//
// asunset can be deployed in two layouts:
//
//   1. **Standalone** — operator runs the asunset repo directly (the
//      Notes demo or a fork-in-place product). The asunset compose.yml
//      is at the deployment root. .env lives next to it.
//
//   2. **Consumer (vendored subtree)** — a downstream product vendors
//      asunset under `vendor/asunset/` per the consuming-template
//      pattern. The product's compose.product.yml lives at the consumer
//      repo root, *outside* vendor/. .env also lives at the consumer
//      root so a single env file feeds both platform and product vars.
//
// The CLI must distinguish these so:
//   - `init` writes .env to the right place (consumer root, not inside
//     vendor/asunset/),
//   - `up` / `down` / etc. include compose.product.yml when present,
//   - and existing .env is found on subsequent runs.

import (
	"strings"
	"os"
	"path/filepath"
)

type Layout struct {
	// AsunsetRoot is the directory containing asunset's own compose.yml.
	// It's the dir docker compose runs from so that `-f compose.yml`
	// and `-f compose.<mode>.yml` (relative paths in launch.go) resolve.
	AsunsetRoot string

	// ConsumerRoot is the deployment root from the operator's POV.
	// Equal to AsunsetRoot in standalone layout. In consumer layout
	// it's the parent of `vendor/asunset/`. .env lives here.
	ConsumerRoot string

	// ProductOverlay is the absolute path to compose.product.yml at the
	// consumer root, or "" if not present (or in standalone layout).
	// Auto-included as `-f` on every compose invocation when set.
	ProductOverlay string

	// Vendored is true when asunset lives under vendor/asunset/ —
	// useful for diagnostic messages.
	Vendored bool
}

// EnvPath returns the canonical .env path for this layout.
func (l Layout) EnvPath() string {
	return filepath.Join(l.ConsumerRoot, ".env")
}

func detectLayout() (Layout, error) {
	asunsetRoot, err := repoRoot()
	if err != nil {
		return Layout{}, err
	}

	layout := Layout{
		AsunsetRoot:  asunsetRoot,
		ConsumerRoot: asunsetRoot,
	}

	// Check whether asunsetRoot looks like `<X>/vendor/asunset` — the
	// canonical consuming-template subtree prefix. We require *both* the
	// final component to be `asunset` and its parent to be `vendor` to
	// avoid false positives on someone whose project happens to live in
	// a directory named `asunset/`.
	parent := filepath.Dir(asunsetRoot)
	if filepath.Base(asunsetRoot) == "asunset" && filepath.Base(parent) == "vendor" {
		consumerRoot := filepath.Dir(parent)
		layout.Vendored = true
		layout.ConsumerRoot = consumerRoot
		// The overlay is compose.product.yml at the consumer root by
		// convention, but consumers with an established deploy layout
		// (OpsRoom: deploy/compose.prod.yml) point at theirs via
		// PRODUCT_COMPOSE in .env — report 92 C.3.
		overlay := filepath.Join(consumerRoot, "compose.product.yml")
		if custom := productComposeFromEnv(consumerRoot); custom != "" {
			if !filepath.IsAbs(custom) {
				custom = filepath.Join(consumerRoot, custom)
			}
			overlay = custom
		}
		if fileExists(overlay) {
			layout.ProductOverlay = overlay
		}
	}

	return layout, nil
}

// productComposeFromEnv reads PRODUCT_COMPOSE from the consumer's .env
// (cheap line scan — .env may not be loadable via loadExistingEnv here
// without recursing into layout detection).
func productComposeFromEnv(consumerRoot string) string {
	data, err := os.ReadFile(filepath.Join(consumerRoot, ".env"))
	if err != nil {
		return ""
	}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if v, ok := strings.CutPrefix(line, "PRODUCT_COMPOSE="); ok {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

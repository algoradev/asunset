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
	"fmt"
	"os"
	"path/filepath"
	"strings"
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

	// Manifest is the parsed product.yaml when the consumer ships one
	// (report 95). Nil otherwise. When present it is the authority for
	// ProductOverlay and drives secret generation, the per-mode
	// caddyfile coherence gate, and one-shot sequencing.
	Manifest *ProductManifest

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
		// Overlay resolution, most-authoritative first:
		//   1. product.yaml (report 95) — the deploy-contract manifest.
		//   2. PRODUCT_COMPOSE in .env (report 92 C.3) — the older
		//      single pointer; still honored, superseded by 1.
		//   3. compose.product.yml at the consumer root by convention.
		manifest, err := loadProductManifest(consumerRoot)
		if err != nil {
			// Fail loud: a present-but-broken manifest must never
			// silently degrade to the conventions below.
			return Layout{}, err
		}
		layout.Manifest = manifest

		overlay := filepath.Join(consumerRoot, "compose.product.yml")
		custom := productComposeFromEnv(consumerRoot)
		if custom != "" {
			if !filepath.IsAbs(custom) {
				custom = filepath.Join(consumerRoot, custom)
			}
			overlay = custom
		}
		if manifest != nil {
			overlay = filepath.Join(consumerRoot, manifest.Compose)
			if custom != "" && custom != overlay {
				fmt.Fprintf(os.Stderr, "note: product.yaml supersedes PRODUCT_COMPOSE "+
					"(%s wins; drop the env var)\n", manifest.Compose)
			}
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

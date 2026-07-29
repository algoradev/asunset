package main

// The product deploy manifest — product.yaml at the consumer root
// (report 95, ratified 2026-07-29; docs/consuming-asunset.md).
//
// The manifest is the consumer's DEPLOY CONTRACT: which compose overlay
// plugs the product in, which Caddyfile serves which mode, which
// secrets the CLI must generate into the single root .env, and which
// one-shots to sequence. It is INFRA-ONLY by ruled boundary: secrets
// are GENERATED never asked, one-shots are SEQUENCED never configured —
// product-domain questions live in the product (the BootstrapGate
// rule). The CLI knows nothing about product service internals beyond
// the names declared here.
//
// Versioned from day one (relay guard): unknown MANIFEST versions fail
// loud; unknown top-level keys fail loud (a typo'd key silently ignored
// is how contracts rot).

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"gopkg.in/yaml.v3"
)

const productManifestName = "product.yaml"
const productManifestVersion = 1

type ProductManifest struct {
	Version int    `yaml:"version"`
	Name    string `yaml:"name"`
	// Compose overlay path, relative to the consumer root.
	Compose string `yaml:"compose"`
	// Per-mode Caddyfile map: mode name → path relative to consumer
	// root. A mode with no entry REFUSES at `up` (coherence gate) —
	// mounting a tailscale-only Caddyfile in TLS mode becomes
	// inexpressible instead of a silent dead ingress.
	Caddyfile map[string]string `yaml:"caddyfile"`
	Env       ManifestEnv       `yaml:"env"`
	// One-shot service names in the product overlay, sequenced by the
	// CLI: Init runs after asunset's own init (mechanical parts only,
	// per the infra-only boundary), Doctor gates before "ready".
	Init   string `yaml:"init"`
	Doctor string `yaml:"doctor"`
}

type ManifestEnv struct {
	// Secrets the CLI GENERATES into the root .env alongside asunset's
	// own. Generate-never-ask: there is deliberately no prompt list.
	Generate []string `yaml:"generate"`
}

// loadProductManifest reads product.yaml at the given consumer root.
// Returns (nil, nil) when absent — the manifest is optional; the older
// PRODUCT_COMPOSE pointer keeps working without it.
func loadProductManifest(consumerRoot string) (*ProductManifest, error) {
	path := filepath.Join(consumerRoot, productManifestName)
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", productManifestName, err)
	}

	// Two-pass: first an open map to catch unknown top-level keys
	// (yaml.v3 has no DisallowUnknownFields on Unmarshal), then the
	// typed decode.
	var raw map[string]any
	if err := yaml.Unmarshal(data, &raw); err != nil {
		return nil, fmt.Errorf("%s: %w", productManifestName, err)
	}
	known := map[string]bool{
		"version": true, "name": true, "compose": true,
		"caddyfile": true, "env": true, "init": true, "doctor": true,
	}
	var unknown []string
	for k := range raw {
		if !known[k] {
			unknown = append(unknown, k)
		}
	}
	if len(unknown) > 0 {
		sort.Strings(unknown)
		return nil, fmt.Errorf("%s: unknown key(s) %v — the manifest is infra-only "+
			"and versioned; see consuming-asunset.md", productManifestName, unknown)
	}

	var m ProductManifest
	if err := yaml.Unmarshal(data, &m); err != nil {
		return nil, fmt.Errorf("%s: %w", productManifestName, err)
	}
	if err := m.validate(consumerRoot); err != nil {
		return nil, err
	}
	return &m, nil
}

func (m *ProductManifest) validate(consumerRoot string) error {
	if m.Version != productManifestVersion {
		return fmt.Errorf("%s: version %d not supported (this CLI speaks version %d) — "+
			"vendor bump one side", productManifestName, m.Version, productManifestVersion)
	}
	if m.Name == "" {
		return fmt.Errorf("%s: name is required", productManifestName)
	}
	if m.Compose == "" {
		return fmt.Errorf("%s: compose is required (the product overlay path)", productManifestName)
	}
	if !fileExists(filepath.Join(consumerRoot, m.Compose)) {
		return fmt.Errorf("%s: compose %q not found at the consumer root", productManifestName, m.Compose)
	}
	for mode, path := range m.Caddyfile {
		switch Mode(mode) {
		case ModeTailscale, ModeTLSInternal, ModeTLSOperator, ModeTLSAcme:
		default:
			return fmt.Errorf("%s: caddyfile declares unknown mode %q", productManifestName, mode)
		}
		if !fileExists(filepath.Join(consumerRoot, path)) {
			return fmt.Errorf("%s: caddyfile for mode %s (%q) not found", productManifestName, mode, path)
		}
	}
	return nil
}

// CaddyfileFor returns the declared Caddyfile for a mode. Plain mode
// has no caddy and never needs one. For caddy-bearing modes, a missing
// entry is the coherence refusal — the trap-#3 class made structural.
func (m *ProductManifest) CaddyfileFor(mode Mode) (string, error) {
	if mode == ModePlain || mode == "" {
		return "", nil
	}
	if len(m.Caddyfile) == 0 {
		// No map at all: the product forks asunset's web (paved path)
		// or hasn't declared foreign ingress — the generated Caddyfile
		// stands, nothing to gate.
		return "", nil
	}
	if p, ok := m.Caddyfile[string(mode)]; ok {
		return p, nil
	}
	declared := make([]string, 0, len(m.Caddyfile))
	for k := range m.Caddyfile {
		declared = append(declared, k)
	}
	sort.Strings(declared)
	return "", fmt.Errorf("mode %s has no caddyfile entry in %s (declared: %v) — "+
		"a foreign UI must declare its ingress per mode; see consuming-asunset.md §5b",
		mode, productManifestName, declared)
}

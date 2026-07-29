package main

// Product-declared secret generation (report 95, env.generate).
//
// One root .env, one writer: the product's manifest lists env keys the
// CLI must GENERATE (never ask — the ruled boundary), and they land in
// the same file as asunset's ten, under a labeled block. Idempotent:
// keys already present (any writer, any value) are left untouched, so
// re-running init never rotates a product secret.

import (
	"fmt"
	"os"
	"strings"
)

const productSecretHeader = "# ---- product secrets (generated from product.yaml) ----"

// ensureProductSecrets appends any missing manifest-declared secrets to
// the .env at envPath. Returns the keys it generated.
func ensureProductSecrets(envPath string, manifest *ProductManifest) ([]string, error) {
	if manifest == nil || len(manifest.Env.Generate) == 0 {
		return nil, nil
	}
	data, err := os.ReadFile(envPath)
	if err != nil {
		return nil, fmt.Errorf("read .env for product secrets: %w", err)
	}
	present := map[string]bool{}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if k, _, ok := strings.Cut(line, "="); ok && !strings.HasPrefix(line, "#") {
			present[strings.TrimSpace(k)] = true
		}
	}

	var added []string
	var b strings.Builder
	for _, key := range manifest.Env.Generate {
		if present[key] {
			continue
		}
		val, err := randString(24)
		if err != nil {
			return nil, err
		}
		fmt.Fprintf(&b, "%s=%s\n", key, val)
		added = append(added, key)
	}
	if len(added) == 0 {
		return nil, nil
	}

	out := string(data)
	if !strings.HasSuffix(out, "\n") {
		out += "\n"
	}
	if !strings.Contains(out, productSecretHeader) {
		out += "\n" + productSecretHeader + "\n"
	}
	out += b.String()
	if err := os.WriteFile(envPath, []byte(out), 0o600); err != nil {
		return nil, fmt.Errorf("write product secrets: %w", err)
	}
	return added, nil
}

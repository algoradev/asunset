package main

import (
	"os"
	"path/filepath"
	"testing"
)

// Report 92 C.3: consumers with an established deploy layout point the
// CLI at their overlay via PRODUCT_COMPOSE in .env instead of renaming
// to the conventional compose.product.yml.

func TestProductComposeEnvOverride(t *testing.T) {
	root := t.TempDir()
	deploy := filepath.Join(root, "deploy")
	if err := os.MkdirAll(deploy, 0o755); err != nil {
		t.Fatal(err)
	}
	custom := filepath.Join(deploy, "compose.prod.yml")
	if err := os.WriteFile(custom, []byte("services: {}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, ".env"),
		[]byte("FOO=bar\nPRODUCT_COMPOSE=deploy/compose.prod.yml\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	got := productComposeFromEnv(root)
	if got != "deploy/compose.prod.yml" {
		t.Fatalf("productComposeFromEnv = %q", got)
	}
}

func TestProductComposeAbsentIsEmpty(t *testing.T) {
	root := t.TempDir()
	if got := productComposeFromEnv(root); got != "" {
		t.Fatalf("expected empty without .env, got %q", got)
	}
}

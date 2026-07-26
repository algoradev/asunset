package main

import (
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"testing"
)

// v1.1 deploy-tooling closure: init provisions a persistent session-
// signing key so no real deployment runs on the ephemeral dev fallback
// (the doctor warns on exactly this).

func TestGenerateSecretsProvisionsSessionKey(t *testing.T) {
	cfg := newConfig()
	if err := generateSecrets(&cfg); err != nil {
		t.Fatal(err)
	}
	b64 := cfg.Secrets.SessionTokenKeyB64
	if b64 == "" {
		t.Fatal("SESSION_TOKEN_PRIVATE_KEY_B64 not generated")
	}
	raw, err := base64.StdEncoding.DecodeString(b64)
	if err != nil {
		t.Fatalf("not valid base64: %v", err)
	}
	block, _ := pem.Decode(raw)
	if block == nil || block.Type != "PRIVATE KEY" {
		t.Fatal("decoded value is not a PEM PRIVATE KEY block")
	}
	if _, err := x509.ParsePKCS8PrivateKey(block.Bytes); err != nil {
		t.Fatalf("not a parseable PKCS8 key: %v", err)
	}
}

func TestEnsureSessionKeyPreservesExisting(t *testing.T) {
	cfg := newConfig()
	cfg.Secrets.SessionTokenKeyB64 = "operator-supplied"
	if err := ensureSessionKey(&cfg); err != nil {
		t.Fatal(err)
	}
	if cfg.Secrets.SessionTokenKeyB64 != "operator-supplied" {
		t.Fatal("ensureSessionKey overwrote an existing key")
	}
}

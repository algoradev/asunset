package main

import (
	cryptorand "crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"crypto/rand"
	"fmt"
	"math/big"
)

// Secrets are crypto-random alphanumeric. No symbols — avoids quoting
// surprises in the generated .env across shells (bash/zsh/fish).

const charset = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

func randString(n int) (string, error) {
	b := make([]byte, n)
	max := big.NewInt(int64(len(charset)))
	for i := range b {
		idx, err := rand.Int(rand.Reader, max)
		if err != nil {
			return "", fmt.Errorf("generate random: %w", err)
		}
		b[i] = charset[idx.Int64()]
	}
	return string(b), nil
}

func generateSecrets(cfg *Config) error {
	pairs := []struct {
		dst *string
		n   int
	}{
		{&cfg.Secrets.KeycloakAdminPass, 24},
		{&cfg.Secrets.KeycloakAPISecret, 32},
		{&cfg.Secrets.OpenFGAAPIKey, 32},
		{&cfg.Secrets.PostgresSuperPass, 24},
		{&cfg.Secrets.AppOwnerPass, 24},
		{&cfg.Secrets.AppUserPass, 24},
		{&cfg.Secrets.KcDbPass, 24},
		{&cfg.Secrets.FgaDbPass, 24},
	}
	for _, p := range pairs {
		v, err := randString(p.n)
		if err != nil {
			return err
		}
		*p.dst = v
	}
	cfg.Secrets.KeycloakAdmin = "admin"
	if err := ensureSessionKey(cfg); err != nil {
		return err
	}
	return nil
}

// ensureSessionKey generates the agent-session signing key when absent —
// called on BOTH the fresh-generate and reuse paths, so pre-v1.1 .env
// files gain a persistent key on their next init instead of running on
// the ephemeral dev fallback forever.
func ensureSessionKey(cfg *Config) error {
	if cfg.Secrets.SessionTokenKeyB64 != "" {
		return nil
	}
	key, err := rsa.GenerateKey(cryptorand.Reader, 2048)
	if err != nil {
		return err
	}
	der, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		return err
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der})
	cfg.Secrets.SessionTokenKeyB64 = base64.StdEncoding.EncodeToString(pemBytes)
	return nil
}

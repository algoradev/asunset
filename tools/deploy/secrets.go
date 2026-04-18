package main

import (
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
	return nil
}

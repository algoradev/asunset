package main

import (
	"bufio"
	"os"
	"strings"
)

// ExistingEnv captures a best-effort read of the repo's .env so the
// wizard can offer to reuse its secrets on re-runs. We parse line by
// line (KEY=VALUE, ignore comments/blank lines) rather than pulling a
// dotenv dep; the file is small and ours.

type ExistingEnv struct {
	Path    string
	Present bool
	Vars    map[string]string
}

func loadExistingEnv() (ExistingEnv, error) {
	layout, err := detectLayout()
	if err != nil {
		return ExistingEnv{}, err
	}
	path := layout.EnvPath()
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return ExistingEnv{Path: path, Present: false}, nil
		}
		return ExistingEnv{Path: path}, err
	}
	defer f.Close()

	vars := map[string]string{}
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		vars[strings.TrimSpace(k)] = strings.TrimSpace(v)
	}
	return ExistingEnv{Path: path, Present: true, Vars: vars}, scanner.Err()
}

// hasAllRequiredSecrets decides whether the existing .env is useful for
// a reuse-path: we need every DB/service secret, otherwise the config
// can't authenticate and the user would hit the mismatch we're trying
// to avoid.
func (e ExistingEnv) hasAllRequiredSecrets() bool {
	required := []string{
		"KEYCLOAK_ADMIN", "KEYCLOAK_ADMIN_PASSWORD",
		"KEYCLOAK_API_CLIENT_SECRET",
		"OPENFGA_API_KEY",
		"POSTGRES_SUPERUSER_PASSWORD",
		"APP_DB_OWNER_PASSWORD", "APP_DB_PASSWORD",
		"KC_DB_PASSWORD", "FGA_DB_PASSWORD",
	}
	for _, k := range required {
		if e.Vars[k] == "" {
			return false
		}
	}
	return true
}

func (e ExistingEnv) fillSecrets(cfg *Config) {
	cfg.Secrets = Secrets{
		KeycloakAdmin:     e.Vars["KEYCLOAK_ADMIN"],
		KeycloakAdminPass: e.Vars["KEYCLOAK_ADMIN_PASSWORD"],
		KeycloakAPISecret: e.Vars["KEYCLOAK_API_CLIENT_SECRET"],
		OpenFGAAPIKey:     e.Vars["OPENFGA_API_KEY"],
		PostgresSuperPass: e.Vars["POSTGRES_SUPERUSER_PASSWORD"],
		AppOwnerPass:      e.Vars["APP_DB_OWNER_PASSWORD"],
		AppUserPass:       e.Vars["APP_DB_PASSWORD"],
		KcDbPass:          e.Vars["KC_DB_PASSWORD"],
		FgaDbPass:         e.Vars["FGA_DB_PASSWORD"],
		// Absent in pre-v1.1 .envs — deliberately NOT in the reuse-
		// required list; ensureSessionKey generates it on next init.
		SessionTokenKeyB64: e.Vars["SESSION_TOKEN_PRIVATE_KEY_B64"],
	}
}

package main

// Config is the single source of truth for the wizard's collected data.
// Every generator reads from it; no other shared state.

type Mode string

const (
	ModePlain       Mode = "plain"
	ModeTLSInternal Mode = "tls-internal"
	ModeTLSOperator Mode = "tls-operator"
	ModeTLSAcme     Mode = "tls-acme"
	ModeTailscale   Mode = "tailscale"
)

type Config struct {
	Mode Mode

	// TLS hostnames (unused in plain + tailscale modes — tailscale uses
	// one hostname with path-based routing, not three subdomains).
	WebHost  string
	AuthHost string
	APIHost  string

	// Operator cert paths (tls-operator only)
	CertPath string
	KeyPath  string

	// ACME email (tls-acme only)
	AcmeEmail string

	// Tailscale MagicDNS FQDN (tailscale mode only), e.g.
	// "asunset.tail-abc123.ts.net". Tailscale serve terminates TLS
	// externally; Caddy inside the compose network runs plain HTTP
	// and does path-based routing.
	TailscaleHost string

	// DevLoopback marks the `asunset dev` flavor: the tailscale
	// (path-multiplexed caddy) topology served on http://127.0.0.1:5173
	// with NO tailnet — TAILSCALE_HOST stays empty; WEB_BASE_URL /
	// KC_BASE_URL overrides carry the loopback origin instead.
	DevLoopback bool

	// WipeVolumes is set when the user chose to regenerate secrets on
	// top of an existing deployment. The launch step respects it by
	// running `compose down -v` before `up` so Postgres init re-seeds
	// with the fresh passwords.
	WipeVolumes bool

	Secrets Secrets
}

type Secrets struct {
	KeycloakAdmin     string
	KeycloakAdminPass string
	KeycloakAPISecret string
	OpenFGAAPIKey     string
	PostgresSuperPass string
	AppOwnerPass      string
	AppUserPass       string
	KcDbPass          string
	FgaDbPass         string
	// base64 PEM RSA key signing agent session tokens (D4 mint) —
	// generated so deployments never run on the ephemeral dev fallback.
	SessionTokenKeyB64 string
}

func newConfig() Config {
	return Config{
		WebHost:  "asunset.local",
		AuthHost: "auth.asunset.local",
		APIHost:  "api.asunset.local",
	}
}

// IsTLS means "caddy terminates TLS itself" — does NOT include Tailscale
// mode, which uses Tailscale serve as the external TLS layer.
func (c Config) IsTLS() bool {
	switch c.Mode {
	case ModeTLSInternal, ModeTLSOperator, ModeTLSAcme:
		return true
	}
	return false
}

func (c Config) IsTailscale() bool { return c.Mode == ModeTailscale }

// Exported so text/template can resolve them as field references.

const devLoopbackOrigin = "http://127.0.0.1:5173"

func (c Config) WebURL() string {
	switch {
	case c.DevLoopback:
		return devLoopbackOrigin
	case c.IsTLS():
		return "https://" + c.WebHost
	case c.IsTailscale():
		return "https://" + c.TailscaleHost
	}
	return "http://localhost:3000"
}

func (c Config) AuthURL() string {
	switch {
	case c.DevLoopback:
		return devLoopbackOrigin + "/auth"
	case c.IsTLS():
		return "https://" + c.AuthHost
	case c.IsTailscale():
		return "https://" + c.TailscaleHost + "/auth"
	}
	return "http://localhost:8080"
}

func (c Config) APIURL() string {
	switch {
	case c.DevLoopback:
		return devLoopbackOrigin + "/api"
	case c.IsTLS():
		return "https://" + c.APIHost
	case c.IsTailscale():
		return "https://" + c.TailscaleHost + "/api"
	}
	return "http://localhost:8000"
}

// KeycloakInternalURL is the in-network URL the api uses to talk to
// Keycloak (JWKS, token introspection). Tailnet mode runs Keycloak with
// `--http-relative-path=/auth` so Caddy can path-multiplex one hostname,
// which means *every* Keycloak URL — internal too — needs the /auth
// prefix. Plain + TLS modes don't set the relative path (TLS uses
// subdomains, plain uses host-only) so the bare URL is correct.
//
// Bug history: this method exists because writing a bare URL in tailnet
// mode caused the api to 404 on JWKS — invisible until first
// authenticated request, which then 500'd. See the centum-dashboard
// portability report's B-KCURL entry.
func (c Config) KeycloakInternalURL() string {
	if c.IsTailscale() {
		return "http://keycloak:8080/auth"
	}
	return "http://keycloak:8080"
}

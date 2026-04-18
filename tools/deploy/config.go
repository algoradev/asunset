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

func (c Config) WebURL() string {
	switch {
	case c.IsTLS():
		return "https://" + c.WebHost
	case c.IsTailscale():
		return "https://" + c.TailscaleHost
	}
	return "http://localhost:3000"
}

func (c Config) AuthURL() string {
	switch {
	case c.IsTLS():
		return "https://" + c.AuthHost
	case c.IsTailscale():
		return "https://" + c.TailscaleHost + "/auth"
	}
	return "http://localhost:8080"
}

func (c Config) APIURL() string {
	switch {
	case c.IsTLS():
		return "https://" + c.APIHost
	case c.IsTailscale():
		return "https://" + c.TailscaleHost + "/api"
	}
	return "http://localhost:8000"
}

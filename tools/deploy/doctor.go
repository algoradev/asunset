package main

// asunset doctor — preflight self-checks (the DX-list item every
// incident kept re-justifying: stale issuer env, /auth-suffix drift,
// unauthenticated probes, ephemeral session keys, port exposure).
//
// Two tiers:
//   static — .env/mode coherence; always runs, no dependencies.
//   live   — best-effort probes of the running stack (api health,
//            Keycloak discovery vs configured issuer, session JWKS,
//            feature-reconcile drift via the machine operator
//            identity). Skips cleanly when the stack is down.
//
// Design rule agreed with the consumer doctor (K3): asunset doctor
// asserts the PLATFORM's own consistency; it never mutates anything —
// drift fixes go through the audited endpoints.

import (
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

type checkStatus string

const (
	statusOK   checkStatus = "ok"
	statusWarn checkStatus = "warn"
	statusFail checkStatus = "fail"
	statusSkip checkStatus = "skip"
)

type checkResult struct {
	Name   string      `json:"name"`
	Status checkStatus `json:"status"`
	Detail string      `json:"detail"`
}

func check(name string, st checkStatus, detail string) checkResult {
	return checkResult{Name: name, Status: st, Detail: detail}
}

// --- static checks (pure over the parsed .env — unit-tested) --------------

func doctorStaticChecks(vars map[string]string) []checkResult {
	var out []checkResult
	mode := vars["ASUNSET_MODE"]
	get := func(k string) string { return strings.TrimSpace(vars[k]) }

	// mode sanity
	switch mode {
	case "plain", "tls-internal", "tls-operator", "tls-acme", "tailscale":
		out = append(out, check("mode", statusOK, "ASUNSET_MODE="+mode))
	case "":
		out = append(out, check("mode", statusWarn, "ASUNSET_MODE unset — mode-specific checks limited"))
	default:
		out = append(out, check("mode", statusFail, "unknown ASUNSET_MODE "+mode))
	}
	isTailscale := mode == "tailscale"
	isTLS := strings.HasPrefix(mode, "tls-")

	// ASUNSET_ENV: the api types it Literal["dev","staging","prod"] and
	// refuses anything else at boot. A missing line is fine (compose
	// defaults to dev since the 663c527331f7 trap); a present-but-wrong
	// value — "production", "" — kills the api with a pydantic error the
	// operator meets only after deploy. Named incident: kestrel's
	// overlay shipped "production" through the whole adoption, masked
	// only because init writes the line.
	switch env := get("ASUNSET_ENV"); env {
	case "dev", "staging", "prod":
		out = append(out, check("asunset-env", statusOK, "ASUNSET_ENV="+env))
	case "":
		out = append(out, check("asunset-env", statusOK,
			"ASUNSET_ENV unset — compose defaults to dev"))
	default:
		out = append(out, check("asunset-env", statusFail, fmt.Sprintf(
			"ASUNSET_ENV=%q is not one of dev|staging|prod — asunset-api will refuse to boot (pydantic Literal)", env)))
	}

	// The classic: the SPA and the API must agree on the public issuer
	// base (a stale VITE_KEYCLOAK_URL bakes the wrong URL into the web
	// bundle; a stale KEYCLOAK_PUBLIC_URL 401s every API request).
	pub, vite := get("KEYCLOAK_PUBLIC_URL"), get("VITE_KEYCLOAK_URL")
	switch {
	case pub == "" || vite == "":
		out = append(out, check("issuer-coherence", statusFail,
			"KEYCLOAK_PUBLIC_URL and VITE_KEYCLOAK_URL must both be set"))
	case pub != vite:
		out = append(out, check("issuer-coherence", statusFail, fmt.Sprintf(
			"KEYCLOAK_PUBLIC_URL (%s) != VITE_KEYCLOAK_URL (%s) — the web bundle and the API "+
				"validate different issuers; logins will fail with issuer mismatch", pub, vite)))
	default:
		out = append(out, check("issuer-coherence", statusOK, pub))
	}

	// /auth path-prefix coherence (the B-KCURL landmine): path-routed
	// modes run Keycloak under /auth on BOTH the public and internal
	// sides; plain mode on neither.
	internal := get("KEYCLOAK_INTERNAL_URL")
	pathRouted := isTailscale // tls modes use per-service hosts, no /auth prefix
	switch {
	case internal == "":
		out = append(out, check("internal-url", statusFail, "KEYCLOAK_INTERNAL_URL unset"))
	case pathRouted && !strings.HasSuffix(internal, "/auth"):
		out = append(out, check("internal-url", statusFail,
			"tailscale mode requires KEYCLOAK_INTERNAL_URL to end in /auth "+
				"(Keycloak runs with --http-relative-path=/auth); JWKS fetches will 404"))
	case !pathRouted && !isTLS && strings.HasSuffix(internal, "/auth"):
		out = append(out, check("internal-url", statusFail,
			"plain mode must NOT have /auth on KEYCLOAK_INTERNAL_URL; JWKS fetches will 404"))
	default:
		out = append(out, check("internal-url", statusOK, internal))
	}

	// Remote-host declarations must match the mode.
	ts := get("TAILSCALE_HOST")
	switch {
	case isTailscale && ts == "":
		out = append(out, check("remote-host", statusFail,
			"tailscale mode with TAILSCALE_HOST unset — keycloak-init will FATAL (by design)"))
	case isTailscale && !strings.Contains(pub, ts):
		out = append(out, check("remote-host", statusFail, fmt.Sprintf(
			"KEYCLOAK_PUBLIC_URL (%s) does not contain TAILSCALE_HOST (%s) — stale env from "+
				"a previous mode; logins will fail", pub, ts)))
	case !isTailscale && ts != "" && strings.Contains(pub, "localhost"):
		out = append(out, check("remote-host", statusWarn,
			"TAILSCALE_HOST set but mode/public URL are local — leftover from a tailnet experiment?"))
	default:
		out = append(out, check("remote-host", statusOK, "consistent with mode"))
	}

	// Session-token signing key (D4 mint): empty = ephemeral per-process
	// key — agent sessions die on every api restart.
	if get("SESSION_TOKEN_PRIVATE_KEY_B64") == "" {
		out = append(out, check("session-key", statusWarn,
			"SESSION_TOKEN_PRIVATE_KEY_B64 unset — agent sessions will NOT survive api "+
				"restarts (fine for dev; set a persistent key for any real deployment: "+
				"openssl genrsa 2048 | base64 -w0)"))
	} else {
		out = append(out, check("session-key", statusOK, "persistent key configured"))
	}

	// D6 audiences: informational.
	if aud := get("KEYCLOAK_EXTRA_AUDIENCES"); aud != "" {
		out = append(out, check("extra-audiences", statusOK, aud))
	} else {
		out = append(out, check("extra-audiences", statusSkip,
			"none configured — token aud is [asunset-api] only"))
	}

	return out
}

// --- live checks (best-effort HTTP against the running stack) -------------

// edgeAuthRouteCheck probes /auth through the caddy front door — the
// route every browser login depends on. Skips cleanly in plain mode
// (no caddy) and when the edge itself is down; fails loudly when the
// edge answers but /auth doesn't reach Keycloak (the foreign-UI
// Caddyfile-swap mistake, or a broken generated file).
func edgeAuthRouteCheck(vars map[string]string, realm string) checkResult {
	const name = "edge-auth-route"
	mode := vars["ASUNSET_MODE"]
	discoveryPath := "/auth/realms/" + realm + "/.well-known/openid-configuration"

	var edgeURL string
	client := &http.Client{Timeout: 5 * time.Second}
	switch {
	case mode == "tailscale":
		edgeURL = "http://127.0.0.1:5173" + discoveryPath
	case strings.HasPrefix(mode, "tls-"):
		authHost := strings.TrimSpace(vars["TLS_AUTH_HOST"])
		if authHost == "" {
			return check(name, statusSkip, "TLS mode but TLS_AUTH_HOST unset")
		}
		// Probe caddy on loopback with SNI/Host for the auth vhost;
		// the internal-CA / operator cert won't chain from the host
		// trust store, and that's fine — this checks ROUTING.
		client.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{
				ServerName:         authHost,
				InsecureSkipVerify: true,
			},
		}
		req, _ := http.NewRequest("GET", "https://127.0.0.1:443"+discoveryPath, nil)
		req.Host = authHost
		resp, err := client.Do(req)
		if err != nil {
			return check(name, statusSkip,
				"caddy edge not reachable on :443 — stack down or ingress external? ("+err.Error()+")")
		}
		return edgeAuthRouteVerdict(name, resp, vars, realm)
	default:
		if mode == "" {
			mode = "unset"
		}
		return check(name, statusSkip, "no caddy edge in mode "+mode)
	}

	resp, err := client.Get(edgeURL)
	if err != nil {
		return check(name, statusSkip,
			"caddy edge not reachable at "+edgeURL+" — stack down? ("+err.Error()+")")
	}
	return edgeAuthRouteVerdict(name, resp, vars, realm)
}

func edgeAuthRouteVerdict(name string, resp *http.Response, vars map[string]string, realm string) checkResult {
	body, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != 200 {
		return check(name, statusFail, fmt.Sprintf(
			"HTTP %d for /auth discovery through the front door — if you replaced the "+
				"Caddyfile (foreign-UI recipe), the verbatim /auth block is the non-negotiable; "+
				"see consuming-asunset.md §5b", resp.StatusCode))
	}
	var disc struct {
		Issuer string `json:"issuer"`
	}
	expected := strings.TrimSuffix(vars["KEYCLOAK_PUBLIC_URL"], "/") + "/realms/" + realm
	if json.Unmarshal(body, &disc) != nil || disc.Issuer == "" {
		return check(name, statusFail, "front door answered /auth but no issuer in discovery doc")
	}
	if disc.Issuer != expected {
		return check(name, statusWarn, fmt.Sprintf(
			"front-door issuer %s != expected %s", disc.Issuer, expected))
	}
	return check(name, statusOK, "front door routes /auth → "+disc.Issuer)
}

func localKCBase(vars map[string]string) string {
	internal := vars["KEYCLOAK_INTERNAL_URL"]
	// in-network DNS isn't resolvable from the host
	return strings.Replace(internal, "http://keycloak:8080", "http://localhost:8080", 1)
}

func doctorLiveChecks(vars map[string]string) []checkResult {
	var out []checkResult
	client := &http.Client{Timeout: 5 * time.Second}
	apiPort := vars["API_PORT"]
	if apiPort == "" {
		apiPort = "8000"
	}
	apiBase := "http://localhost:" + apiPort

	// api liveness gates the rest. The api-plane live checks target
	// asunset's demo api — a foreign-gate consumer profiles it out, so
	// say that instead of the misleading "stack down".
	resp, err := client.Get(apiBase + "/healthz")
	if err != nil {
		detail := "api not reachable at " + apiBase + " — stack down? live checks skipped"
		if layout, lerr := detectLayout(); lerr == nil && layout.Manifest != nil {
			detail = "foreign-gate consumer (" + layout.Manifest.Name + "): demo api not deployed — " +
				"api-plane checks apply at the product gate post-adoption; " +
				"edge-auth-route + static tier are the platform checks here"
		}
		out = append(out, check("api-live", statusSkip, detail))
		return out
	}
	resp.Body.Close()
	out = append(out, check("api-live", statusOK, apiBase))

	// readiness with the per-dependency breakdown surfaced.
	if resp, err = client.Get(apiBase + "/readyz"); err == nil {
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		var ready struct {
			Status string `json:"status"`
			Checks map[string]struct {
				Status string `json:"status"`
				Error  string `json:"error"`
			} `json:"checks"`
		}
		if json.Unmarshal(body, &ready) == nil && ready.Status == "ok" {
			out = append(out, check("api-ready", statusOK, "db+openfga+jwks reachable"))
		} else {
			var failing []string
			for name, c := range ready.Checks {
				if c.Status != "ok" {
					failing = append(failing, name+": "+c.Error)
				}
			}
			out = append(out, check("api-ready", statusFail, strings.Join(failing, "; ")))
		}
	}

	// Keycloak discovery — and the issuer it ADVERTISES must be the one
	// validation is configured for (the mismatch the guard 401s on).
	realm := vars["KEYCLOAK_REALM"]
	if realm == "" {
		realm = "asunset"
	}
	discoveryURL := localKCBase(vars) + "/realms/" + realm + "/.well-known/openid-configuration"
	if resp, err = client.Get(discoveryURL); err != nil {
		out = append(out, check("keycloak-discovery", statusFail, err.Error()))
	} else {
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		var disc struct {
			Issuer string `json:"issuer"`
		}
		expected := strings.TrimSuffix(vars["KEYCLOAK_PUBLIC_URL"], "/") + "/realms/" + realm
		if json.Unmarshal(body, &disc) != nil || disc.Issuer == "" {
			out = append(out, check("keycloak-discovery", statusFail, "no issuer in discovery doc"))
		} else if disc.Issuer != expected {
			out = append(out, check("keycloak-discovery", statusWarn, fmt.Sprintf(
				"advertised issuer %s != expected %s (KC hostname config vs KEYCLOAK_PUBLIC_URL "+
					"— tokens minted through a browser at the advertised URL will be rejected)",
				disc.Issuer, expected)))
		} else {
			out = append(out, check("keycloak-discovery", statusOK, disc.Issuer))
		}
	}

	// Front-door /auth route through the caddy edge. The generated
	// Caddyfile always carries it; a foreign-UI consumer owns their
	// Caddyfile (consuming-asunset.md §5b) and the /auth block is the
	// recipe's non-negotiable — this is where forgetting it surfaces
	// before a browser does.
	out = append(out, edgeAuthRouteCheck(vars, realm))

	// Session-token JWKS (second issuer of contract §5.1a).
	if resp, err = client.Get(apiBase + "/platform/sessions/jwks"); err == nil {
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		var jwks struct {
			Keys []map[string]any `json:"keys"`
		}
		if json.Unmarshal(body, &jwks) == nil && len(jwks.Keys) > 0 {
			out = append(out, check("session-jwks", statusOK,
				fmt.Sprintf("%d signing key(s) published", len(jwks.Keys))))
		} else {
			out = append(out, check("session-jwks", statusFail, "no keys at /platform/sessions/jwks"))
		}
	}

	// Feature-manifest drift via the machine operator identity
	// (client credentials → reconcile dry_run). Read-only by contract.
	token := machineToken(client, vars)
	if token == "" {
		out = append(out, check("feature-drift", statusSkip,
			"could not obtain machine operator token (client credentials) — check "+
				"KEYCLOAK_API_CLIENT_ID/SECRET, and that keycloak-init ran (grants platform_support)"))
		return out
	}
	req, _ := http.NewRequest("POST", apiBase+"/platform/features/reconcile",
		strings.NewReader(`{"dry_run": true}`))
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	if resp, err = client.Do(req); err != nil {
		out = append(out, check("feature-drift", statusFail, err.Error()))
	} else {
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		switch resp.StatusCode {
		case 200:
			var rep struct {
				Added   int      `json:"added"`
				Orphans []string `json:"orphans"`
			}
			_ = json.Unmarshal(body, &rep)
			if rep.Added == 0 && len(rep.Orphans) == 0 {
				out = append(out, check("feature-drift", statusOK, "manifest and FGA agree"))
			} else {
				out = append(out, check("feature-drift", statusWarn, fmt.Sprintf(
					"drift: %d grant(s) would be added, %d orphan(s) — apply via "+
						"POST /platform/features/reconcile", rep.Added, len(rep.Orphans))))
			}
		case 409:
			out = append(out, check("feature-drift", statusSkip,
				"no manifest configured or no org yet"))
		default:
			out = append(out, check("feature-drift", statusFail,
				fmt.Sprintf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))))
		}
	}
	return out
}

func machineToken(client *http.Client, vars map[string]string) string {
	realm := vars["KEYCLOAK_REALM"]
	if realm == "" {
		realm = "asunset"
	}
	form := url.Values{
		"grant_type":    {"client_credentials"},
		"client_id":     {vars["KEYCLOAK_API_CLIENT_ID"]},
		"client_secret": {vars["KEYCLOAK_API_CLIENT_SECRET"]},
	}
	resp, err := client.PostForm(
		localKCBase(vars)+"/realms/"+realm+"/protocol/openid-connect/token", form)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	var tok struct {
		AccessToken string `json:"access_token"`
	}
	if json.NewDecoder(resp.Body).Decode(&tok) != nil {
		return ""
	}
	return tok.AccessToken
}

// --- command ---------------------------------------------------------------

func cmdDoctor(args []string) {
	jsonOut := len(args) > 0 && args[0] == "--json"

	env, err := loadExistingEnv()
	if err != nil {
		fmt.Fprintln(os.Stderr, "doctor: cannot resolve layout:", err)
		os.Exit(1)
	}
	if !env.Present {
		fmt.Fprintln(os.Stderr, "doctor: no .env at", env.Path, "— run `asunset init` first")
		os.Exit(1)
	}

	results := doctorStaticChecks(env.Vars)
	results = append(results, doctorLiveChecks(env.Vars)...)

	fails := 0
	if jsonOut {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		_ = enc.Encode(results)
		for _, r := range results {
			if r.Status == statusFail {
				fails++
			}
		}
	} else {
		icons := map[checkStatus]string{
			statusOK: "✓", statusWarn: "!", statusFail: "✗", statusSkip: "-",
		}
		for _, r := range results {
			fmt.Printf("  %s %-20s %s\n", icons[r.Status], r.Name, r.Detail)
			if r.Status == statusFail {
				fails++
			}
		}
		if fails > 0 {
			fmt.Printf("\ndoctor: %d check(s) FAILED\n", fails)
		} else {
			fmt.Println("\ndoctor: all checks passed")
		}
	}
	if fails > 0 {
		os.Exit(1)
	}
}

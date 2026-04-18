package main

import (
	"encoding/json"
	"os/exec"
	"strings"
	"time"
)

// TailscaleState is the handful of `tailscaled` states the wizard cares
// about. "unknown" is a catch-all for socket errors or unparseable JSON.
type TailscaleState string

const (
	TSNotInstalled TailscaleState = "not-installed"
	TSNeedsLogin   TailscaleState = "needs-login"
	TSStopped      TailscaleState = "stopped"
	TSRunning      TailscaleState = "running"
	TSUnknown      TailscaleState = "unknown"
)

type TailscaleStatus struct {
	State   TailscaleState
	DNSName string // populated when Running
	AuthURL string // populated when NeedsLogin
	RawErr  string // populated when Unknown
}

// checkTailscale queries `tailscale status --json` and collapses the
// response into the wizard's state enum. Safe to call when tailscale
// isn't installed — returns TSNotInstalled without erroring.
func checkTailscale() TailscaleStatus {
	if _, err := exec.LookPath("tailscale"); err != nil {
		return TailscaleStatus{State: TSNotInstalled}
	}

	cmd := exec.Command("tailscale", "status", "--json")
	done := make(chan struct{})
	var (
		out []byte
		err error
	)
	go func() {
		out, err = cmd.Output()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		_ = cmd.Process.Kill()
		return TailscaleStatus{State: TSUnknown, RawErr: "timeout querying tailscaled"}
	}
	if err != nil {
		return TailscaleStatus{State: TSUnknown, RawErr: err.Error()}
	}

	var parsed struct {
		BackendState string `json:"BackendState"`
		AuthURL      string `json:"AuthURL"`
		Self         struct {
			DNSName string `json:"DNSName"`
		} `json:"Self"`
	}
	if err := json.Unmarshal(out, &parsed); err != nil {
		return TailscaleStatus{State: TSUnknown, RawErr: "parse: " + err.Error()}
	}

	switch parsed.BackendState {
	case "Running":
		return TailscaleStatus{
			State:   TSRunning,
			DNSName: strings.TrimSuffix(parsed.Self.DNSName, "."),
		}
	case "NeedsLogin":
		return TailscaleStatus{State: TSNeedsLogin, AuthURL: parsed.AuthURL}
	case "Stopped":
		return TailscaleStatus{State: TSStopped}
	default:
		return TailscaleStatus{
			State:  TSUnknown,
			RawErr: "unexpected BackendState: " + parsed.BackendState,
		}
	}
}

// detectTailscaleHost is the lightweight helper the hostname form uses
// to pre-fill the input. Returns only when tailscale is Running AND
// has a valid Self.DNSName. Kept as a separate entry point so the
// preflight and the detect-for-prefill calls are independent.
func detectTailscaleHost() (string, bool) {
	s := checkTailscale()
	if s.State != TSRunning || s.DNSName == "" {
		return "", false
	}
	return s.DNSName, true
}

# asunset CLI

On-prem deployment control for asunset stacks. One binary covers both
first-run setup and day-two operations.

## Commands

| Command            | What it does                                             |
|--------------------|----------------------------------------------------------|
| `asunset init`     | Interactive wizard — generates `.env` + Caddyfile        |
| `asunset up`       | `docker compose up -d` with the right overlay            |
| `asunset down`     | `docker compose down`                                    |
| `asunset restart [svc]` | Restart one service or the whole stack              |
| `asunset logs [svc]`    | Tail logs (all or one service; follows by default)  |
| `asunset ps`       | Show running services                                    |
| `asunset help`     | Show help                                                |

All lifecycle commands read `ASUNSET_MODE` from the generated `.env` and
pick the matching compose overlay (`compose.tls.yml`,
`compose.tailscale.yml`, …) automatically. Operators don't type `-f`
flags.

## Install on a fresh Ubuntu/Debian host

```sh
curl -fsSL https://<product>/install.sh | sudo bash
```

The installer:

1. Verifies Ubuntu/Debian, aborts otherwise.
2. Installs Docker Engine + compose plugin, git, and Go ≥1.22 if missing.
3. Clones the repo to `/opt/asunset` (override with `ASUNSET_HOME=/srv/x`).
4. Builds the `asunset` binary from source.
5. Symlinks `/usr/local/bin/asunset` so it's on PATH for every user.

Re-running is idempotent: deps are skipped if present, the checkout is
fast-forwarded, the binary is rebuilt, the symlink refreshed.

Then:

```sh
sudo asunset init   # wizard: pick mode, secrets, hostnames
sudo asunset up     # start the stack
```

## Deployment modes

`asunset init` asks which TLS strategy fits the environment:

| Mode            | When to use                              | Caddyfile strategy               |
|-----------------|------------------------------------------|----------------------------------|
| `plain`         | Local dev on localhost                   | none (no TLS)                    |
| `tls-internal`  | Dev/staging, self-signed certs           | `tls internal` — Caddy's CA      |
| `tls-operator`  | Typical on-prem with PKI-issued certs    | `tls {cert} {key}` mounted       |
| `tls-acme`      | Public internet                          | Automatic Let's Encrypt          |
| `tailscale`     | Tailnet-only access, MagicDNS + serve    | path-mux on `:5173`              |

Secrets are crypto-random (24–32 char alphanumeric, from `crypto/rand`).
The wizard prints them once at the end; they also land in `.env`
(gitignored). Re-running with a pre-existing `.env` offers a
reuse-secrets path so running Postgres volumes don't mismatch.

## Build from source (developers)

```sh
cd tools/deploy
go build -o asunset ./...
```

## Cross-compile for release

```sh
GOOS=linux GOARCH=amd64 go build -o dist/asunset-linux-amd64 ./...
GOOS=linux GOARCH=arm64 go build -o dist/asunset-linux-arm64 ./...
```

## Tests

```sh
go test ./...
```

`generate_test.go` covers every deployment mode's file generation without
needing a TTY (huh forms are skipped).

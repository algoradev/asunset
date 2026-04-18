# asunset-deploy

Interactive wizard that generates `.env` and `infra/caddy/Caddyfile` for a
new asunset deployment.

## Why it exists

Hospital ops teams won't hand-craft env files, and the number of decisions
required to deploy this template (hostnames, cert strategy, secrets for
every service) is large enough that a guided flow is meaningfully faster
and less error-prone than a README checklist.

## Run it

```sh
cd tools/deploy
go build -o asunset-deploy ./...
cd ../..                           # back to repo root
./tools/deploy/asunset-deploy
```

The wizard must be run from the repo root — it locates the target by
walking upward for `compose.yml`.

## What it generates

Four deployment modes, each with the right `.env` + Caddyfile shape:

| Mode | When to use | Caddyfile |
|---|---|---|
| `plain` | Local dev on localhost | none (no TLS) |
| `tls-internal` | Dev/staging, self-signed certs | `tls internal` — Caddy's embedded CA |
| `tls-operator` | Typical on-prem with PKI-issued certs | `tls {cert} {key}` — mounted from host |
| `tls-acme` | Public internet | Automatic Let's Encrypt |

Secrets are crypto-random (24–32 char alphanumeric, from `crypto/rand`):

- Keycloak admin password
- `asunset-api` client secret
- OpenFGA preshared API key
- Postgres superuser password
- App DB owner + app user passwords
- Keycloak DB password
- OpenFGA DB password

The wizard prints credentials once at the end. They're also written to
`.env` (gitignored), but the printed summary is the only time the user
sees them in a copy-friendly form.

## Cross-compile for operator distribution

```sh
GOOS=linux   GOARCH=amd64 go build -o dist/asunset-deploy-linux-amd64   ./...
GOOS=linux   GOARCH=arm64 go build -o dist/asunset-deploy-linux-arm64   ./...
GOOS=darwin  GOARCH=amd64 go build -o dist/asunset-deploy-darwin-amd64  ./...
GOOS=darwin  GOARCH=arm64 go build -o dist/asunset-deploy-darwin-arm64  ./...
```

Binaries are self-contained — operators need only Docker on the target host.

## Tests

```sh
go test ./...
```

`generate_test.go` exercises every deployment mode's file generation
without needing a TTY (huh forms are skipped).

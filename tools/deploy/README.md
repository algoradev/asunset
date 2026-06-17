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

## Non-interactive init (CI / CodePipeline / Lightsail)

`asunset init` with no args runs the interactive wizard. Pass any flags (or a
config file) and it runs unattended — for reproducible client/consumer
deployments where a wizard breaks pipeline reproducibility.

```sh
# Config-file mode (preferred — one file is the deployment's source of truth)
asunset init --config deploy/asunset.init.yaml --yes

# Flag mode (simple automation)
asunset init --mode tailscale --tailscale-host crm.tail-abc.ts.net --yes
asunset init --mode tls-operator \
  --web-host w.example.com --auth-host a.example.com --api-host p.example.com \
  --cert-path /etc/ssl/full.pem --key-path /etc/ssl/key.pem --yes
```

`--yes` is required (confirms unattended generation). Flags override config-file
values. See `asunset init --help` for the full flag list.

**Config file** — a flat `key: value` file (scalar subset of YAML; `#`
comments allowed):

```yaml
mode: tailscale                 # plain | tls-internal | tls-operator | tls-acme | tailscale
tailscale_host: crm.tail-abc.ts.net
# web_host / auth_host / api_host   for TLS modes
# cert_path / key_path              for tls-operator
# acme_email                        for tls-acme
launch: false                   # write files only (default); true runs docker compose
```

**Secrets.** Omitted secrets are crypto-generated exactly as the wizard does.
For deterministic provisioning, supply them via config-file keys
(`keycloak_admin_password`, `openfga_api_key`, `app_db_password`, …) or the
canonical env vars of the same name (`KEYCLOAK_ADMIN_PASSWORD`, etc.) — handy
with AWS Secrets Manager / SSM injection. Supplied secrets are **not** echoed
to stdout (pipeline logs); pass `--print-secrets` to override.

**Existing `.env`.** Non-interactive runs never silently clobber. If an `.env`
with a complete secret set already exists you must pass exactly one of:

- `--reuse-secrets` — keep the existing secrets and Postgres volumes, just
  rewrite mode/host config.
- `--regenerate-secrets --wipe-volumes` — replace secrets and destroy the old
  volumes (required together, since the old Postgres volume holds the old
  passwords).

Otherwise init fails with a clear message rather than guessing.

Validation (mode validity + per-mode required fields) runs **before** any file
is written, so an invalid combination fails clean.

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

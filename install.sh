#!/usr/bin/env bash
# asunset installer — bootstraps an on-prem Ubuntu/Debian host:
#   - installs docker engine + compose plugin, git, Go toolchain
#   - clones the repo into /opt/asunset (or ${ASUNSET_HOME})
#   - builds the `asunset` CLI and symlinks it onto /usr/local/bin
#
# Usage:
#   curl -fsSL <url>/install.sh | sudo bash
#   sudo ./install.sh [repo-url] [install-dir]
#
# Re-running is idempotent: existing deps are skipped, an existing
# checkout is fast-forwarded, the binary is rebuilt and the symlink
# refreshed.

set -euo pipefail

REPO_URL="${1:-${ASUNSET_REPO:-https://github.com/crossing/asunset.git}}"
INSTALL_DIR="${2:-${ASUNSET_HOME:-/opt/asunset}}"
BIN_LINK="/usr/local/bin/asunset"
GO_VERSION="1.23.4"

c_title() { printf '\033[1;35m%s\033[0m\n' "$*"; }
c_info()  { printf '\033[34m→\033[0m %s\n'  "$*"; }
c_ok()    { printf '\033[32m✓\033[0m %s\n'  "$*"; }
c_warn()  { printf '\033[33m!\033[0m %s\n'  "$*"; }
c_err()   { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; }

die() { c_err "$*"; exit 1; }

[ "$EUID" -eq 0 ] || die "run as root: sudo $0"

c_title "asunset installer"
printf '  repo:    %s\n' "$REPO_URL"
printf '  install: %s\n' "$INSTALL_DIR"
printf '  symlink: %s\n\n' "$BIN_LINK"

# ---- OS gate -----------------------------------------------------------------
[ -r /etc/os-release ] || die "/etc/os-release missing — unsupported OS"
# shellcheck disable=SC1091
. /etc/os-release
case "$ID" in
    ubuntu|debian) ;;
    *) die "unsupported OS: $ID (this installer supports Ubuntu/Debian only)";;
esac
c_ok "OS: $PRETTY_NAME"

# ---- apt dependencies --------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
c_info "updating apt"
apt-get update -qq
c_info "installing base packages (git, curl, ca-certificates)"
apt-get install -y -qq git curl ca-certificates

# ---- Docker ------------------------------------------------------------------
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    c_ok "docker + compose plugin already present ($(docker --version | awk '{print $3}' | tr -d ,))"
else
    c_info "installing Docker via get.docker.com"
    curl -fsSL https://get.docker.com | sh >/dev/null
    docker compose version >/dev/null 2>&1 || apt-get install -y -qq docker-compose-plugin
    c_ok "docker $(docker --version | awk '{print $3}' | tr -d ,) installed"
fi

# ---- Go (needed to build the CLI from source) --------------------------------
need_go() {
    command -v go >/dev/null 2>&1 || return 0
    local have
    have=$(go env GOVERSION 2>/dev/null | sed 's/go//')
    # need ≥ 1.22 — dumb version sort via sort -V
    if printf '1.22\n%s\n' "$have" | sort -V -C 2>/dev/null; then
        c_ok "go $have (meets ≥1.22)"
        return 1
    fi
    c_warn "go $have is too old (need ≥1.22) — installing newer"
    return 0
}

if need_go; then
    arch=$(dpkg --print-architecture)
    case "$arch" in
        amd64|arm64) ;;
        *) die "unsupported arch: $arch";;
    esac
    tar="go${GO_VERSION}.linux-${arch}.tar.gz"
    c_info "downloading go ${GO_VERSION} (${arch})"
    curl -fsSL "https://go.dev/dl/${tar}" -o "/tmp/${tar}"
    rm -rf /usr/local/go
    tar -C /usr/local -xzf "/tmp/${tar}"
    rm "/tmp/${tar}"
    ln -sf /usr/local/go/bin/go /usr/local/bin/go
    c_ok "go ${GO_VERSION} installed to /usr/local/go"
fi

# ---- fetch or update the repo ------------------------------------------------
if [ -d "$INSTALL_DIR/.git" ]; then
    c_warn "$INSTALL_DIR already exists — fetching latest"
    git -C "$INSTALL_DIR" fetch --tags --quiet
    git -C "$INSTALL_DIR" pull --ff-only --quiet
else
    c_info "cloning $REPO_URL → $INSTALL_DIR"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
fi
c_ok "source at $INSTALL_DIR ($(git -C "$INSTALL_DIR" rev-parse --short HEAD))"

# ---- build the CLI -----------------------------------------------------------
c_info "building asunset CLI"
( cd "$INSTALL_DIR/tools/deploy" && go build -o asunset ./... )
c_ok "built $INSTALL_DIR/tools/deploy/asunset"

# ---- expose on PATH ----------------------------------------------------------
ln -sf "$INSTALL_DIR/tools/deploy/asunset" "$BIN_LINK"
c_ok "symlinked $BIN_LINK → $INSTALL_DIR/tools/deploy/asunset"

echo
c_title "next steps"
printf '  sudo asunset init     # interactive setup (generates .env + Caddyfile)\n'
printf '  sudo asunset up       # start the stack\n'
printf '  asunset help          # all commands\n'

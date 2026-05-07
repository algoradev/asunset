#!/usr/bin/env bash
# Pull the latest asunset into vendor/asunset/ via git subtree.
#
# Run from the consumer repo root. Working tree must be clean — subtree
# pull lands a merge commit and there's no graceful unwind if the merge
# blows up halfway. After the pull, expect to re-port apps/web/
# customizations if asunset did a major UI overhaul; see README.md.
#
# Usage:
#   scripts/update-vendor.sh <upstream-url-or-path> [<branch>]
#
# Examples:
#   scripts/update-vendor.sh git@github.com:you/asunset.git
#   scripts/update-vendor.sh /home/me/Development/asunset main

set -euo pipefail

PREFIX="vendor/asunset"

if [ "$#" -lt 1 ]; then
    echo "usage: $0 <upstream-url-or-path> [<branch>]" >&2
    exit 2
fi

UPSTREAM="$1"
BRANCH="${2:-main}"

if [ -n "$(git status --porcelain)" ]; then
    echo "error: working tree is not clean. Commit or stash first." >&2
    exit 1
fi

if [ ! -d "$PREFIX" ]; then
    echo "error: $PREFIX does not exist. Did you run 'git subtree add' yet?" >&2
    exit 1
fi

echo "Pulling $UPSTREAM ($BRANCH) into $PREFIX..."
git subtree pull --prefix="$PREFIX" "$UPSTREAM" "$BRANCH" --squash

echo
echo "Done. Review the merge commit and re-port any apps/web/ edits if"
echo "the upstream change touched the shell (App.tsx, sidebar, router)."

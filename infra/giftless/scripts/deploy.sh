#!/usr/bin/env bash
# Build the Docker image and ship it to Fly.io. Idempotent.
# Assumes `fly apps create hyperdraft-lfs` and `./scripts/set-secrets.sh` already ran.

set -euo pipefail
cd "$(dirname "$0")/.."

fly deploy --remote-only

echo
echo "Deployed. Smoke test:"
echo "  curl -i https://hyperdraft-lfs.fly.dev/"
echo "  (expect HTTP 200 with a giftless welcome blurb)"

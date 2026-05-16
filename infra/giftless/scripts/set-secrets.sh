#!/usr/bin/env bash
# Push R2 credentials + JWT secret from local .env into Fly secrets.
# Run after `fly apps create hyperdraft-lfs` and before `fly deploy`.

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing. Copy .env.example to .env and fill in values."
  exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

required=(R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_ENDPOINT R2_BUCKET GIFTLESS_JWT_SECRET)
for var in "${required[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: $var is empty in .env"
    exit 1
  fi
done

fly secrets set \
  R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
  R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
  R2_ENDPOINT="$R2_ENDPOINT" \
  R2_BUCKET="$R2_BUCKET" \
  GIFTLESS_JWT_SECRET="$GIFTLESS_JWT_SECRET"

echo
echo "Secrets pushed. Next: ./scripts/deploy.sh"

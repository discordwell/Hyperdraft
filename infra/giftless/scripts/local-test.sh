#!/usr/bin/env bash
# Run giftless in Docker locally against your .env. Useful for verifying
# config before deploying to Fly.io.
#
# Hit http://localhost:8000/ after it starts.

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing." >&2
  exit 1
fi

docker build -t hyperdraft-lfs:local .

docker run --rm -it \
  --env-file .env \
  -p 8000:8000 \
  --name hyperdraft-lfs-local \
  hyperdraft-lfs:local

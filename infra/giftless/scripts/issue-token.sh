#!/usr/bin/env bash
# Mint a JWT that grants git-lfs write access to our giftless server.
# Token is good for 2 hours (matches max_lifetime in giftless.yaml).
#
# Usage:
#   ./scripts/issue-token.sh                              # prints token to stdout
#   ./scripts/issue-token.sh --install discordwell/Hyperdraft   # writes to git credential helper
#
# After --install, `git push` against the repo will authenticate to LFS automatically.

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing. Need GIFTLESS_JWT_SECRET to sign tokens." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

if [[ -z "${GIFTLESS_JWT_SECRET:-}" ]]; then
  echo "ERROR: GIFTLESS_JWT_SECRET unset in .env" >&2
  exit 1
fi

TOKEN=$(GIFTLESS_JWT_SECRET="$GIFTLESS_JWT_SECRET" python3 - <<'PY'
import os, time, jwt
now = int(time.time())
payload = {
    "iss": "hyperdraft-lfs",
    "sub": "writer",
    "iat": now,
    "exp": now + 7200,
    "scopes": ["obj:*"],
}
print(jwt.encode(payload, os.environ["GIFTLESS_JWT_SECRET"], algorithm="HS256"))
PY
)

if [[ "${1:-}" == "--install" ]]; then
  repo="${2:-}"
  if [[ -z "$repo" ]]; then
    echo "Usage: $0 --install <owner/repo>" >&2
    exit 1
  fi
  # Configure a credential entry for the LFS endpoint
  url="https://hyperdraft-lfs.fly.dev/${repo}.git/info/lfs"
  # giftless's JWT basic-auth user is _jwt (the default in JWTAuthenticator)
  git config --global "credential.${url}.username" "_jwt"
  git config --global "credential.${url}.helper" "!f() { echo \"username=_jwt\"; echo \"password=${TOKEN}\"; }; f"
  echo "Installed token for $url (expires in 2h)"
else
  echo "$TOKEN"
fi

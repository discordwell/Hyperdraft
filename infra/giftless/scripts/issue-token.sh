#!/usr/bin/env bash
# Mint a JWT that grants git-lfs write access to our giftless server.
# Tokens are valid for 2 h (matches default_lifetime in giftless.yaml).
#
# Usage:
#   ./scripts/issue-token.sh                                # prints a fresh token to stdout
#   ./scripts/issue-token.sh --install <owner/repo>         # wires a self-minting git credential helper
#   ./scripts/issue-token.sh --status                       # report cached cred's TTL
#
# After --install, git push / git lfs pull against the LFS endpoint will
# invoke this script ON DEMAND to fetch a fresh JWT — no stale-token state can
# accumulate in the credential helper, so git-lfs cannot fall into a
# 401 → reject → fill → 401 retry loop on an expired token.

set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"
cd "$(dirname "$0")/.."

load_secret() {
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
}

mint_token() {
  load_secret
  GIFTLESS_JWT_SECRET="$GIFTLESS_JWT_SECRET" python3 - <<'PY'
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
}

install_helper() {
  local repo="${1:-}"
  if [[ -z "$repo" ]]; then
    echo "Usage: $0 --install <owner/repo>" >&2
    exit 1
  fi
  # The helper SHELLS OUT to this script on every credential fill, so every
  # LFS HTTP request gets a freshly-minted JWT. Pinning a frozen token here
  # (the old behavior) would let git-lfs cache an expired credential and
  # spin forever in a 401-retry loop the moment that token aged out.
  local url="https://hyperdraft-lfs.fly.dev/${repo}.git/info/lfs"
  local host="https://hyperdraft-lfs.fly.dev"
  local helper="!f() { echo \"username=_jwt\"; echo \"password=\$(${SCRIPT_PATH})\"; }; f"
  for scope in "$url" "$host"; do
    git config --global "credential.${scope}.username" "_jwt"
    git config --global "credential.${scope}.helper" "$helper"
  done
  echo "Installed self-minting helper for $url and $host"
  echo "(Each LFS request will invoke ${SCRIPT_PATH} to mint a 2h JWT live.)"
}

report_status() {
  load_secret  # also validates we *can* mint, so a healthy report means a healthy install
  local host="https://hyperdraft-lfs.fly.dev"
  local helper
  helper=$(git config --global --get "credential.${host}.helper" || true)
  if [[ -z "$helper" ]]; then
    echo "No credential helper installed at credential.${host}.*"
    echo "Run: $0 --install <owner/repo>"
    return 1
  fi
  echo "Helper installed at credential.${host}.helper:"
  echo "  $helper"
  echo
  if [[ "$helper" == *"$SCRIPT_PATH"* ]]; then
    echo "Mode: self-minting (calls $(basename "$SCRIPT_PATH") on every fill)"
  else
    echo "Mode: FROZEN TOKEN  ← legacy install, can age out and trap git-lfs"
    echo "   Recommended: re-run \`$0 --install <owner/repo>\` to switch to self-minting."
  fi
  # Materialize whatever the helper would hand to git-lfs RIGHT NOW and decode it.
  local cmd="${helper#!}"
  local password
  password=$(bash -c "$cmd 2>/dev/null" | awk -F= '/^password=/{print substr($0,10); exit}')
  if [[ -z "$password" ]]; then
    echo "WARN: helper returned no password line."
    return 1
  fi
  python3 - "$password" <<'PY'
import base64, json, sys, time
tok = sys.argv[1].strip()
parts = tok.split(".")
if len(parts) != 3:
    print("WARN: cached credential is not a JWT (3 segments).")
    sys.exit(1)
pad = parts[1] + "=" * (-len(parts[1]) % 4)
payload = json.loads(base64.urlsafe_b64decode(pad))
now = int(time.time())
remaining = payload.get("exp", 0) - now
m, s = divmod(max(remaining, 0), 60)
h, m = divmod(m, 60)
status = "EXPIRED" if remaining <= 0 else f"valid for {h}h{m:02d}m{s:02d}s"
print(f"Current token: iss={payload.get('iss')!r} sub={payload.get('sub')!r} scopes={payload.get('scopes')}")
print(f"               iat={payload.get('iat')} exp={payload.get('exp')} ({status})")
PY
}

case "${1:-}" in
  --install)
    shift
    install_helper "${1:-}"
    ;;
  --status)
    report_status
    ;;
  "")
    mint_token
    ;;
  *)
    echo "Unknown argument: $1" >&2
    echo "Usage: $0 [--install <owner/repo> | --status]" >&2
    exit 1
    ;;
esac

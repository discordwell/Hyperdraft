#!/usr/bin/env bash
# Refresh the hyperdraft container's Claude Code OAuth credentials.
#
# The hyperdraft-hyperdraft-1 container on ovh2 spawns `claude -p`
# subprocesses to play ultra-agent matches. Those use OAuth via the
# Claude Max subscription (free per token) when /root/.claude/.credentials.json
# inside the container is valid, and fail with 401 when stale.
#
# The OAuth tokens rotate periodically (e.g. on `claude /logout`, on
# subscription changes, or naturally on refresh-token chain churn). This
# script re-extracts the live OAuth credentials from the host Mac's
# Keychain and pushes them into the container. Idempotent; safe to rerun.
#
# Usage:
#   bash scripts/refresh_container_oauth.sh         # update creds only
#   bash scripts/refresh_container_oauth.sh --restart  # also restart the container
#
# Requires:
#   - Running on the host Mac (uses /usr/bin/security to read Keychain)
#   - ssh access to ovh2
#   - ANTHROPIC_API_KEY MUST stay unset in /opt/hyperdraft/.env. Otherwise
#     the spawned `claude` prefers the API key over OAuth and bills Opus
#     at full API rates — the whole point of OAuth here is the Max sub's
#     free per-token throughput.

set -euo pipefail

SSH_HOST="${SSH_HOST:-ovh2}"
CONTAINER="${CONTAINER:-hyperdraft-hyperdraft-1}"
COMPOSE_DIR="${COMPOSE_DIR:-/opt/hyperdraft}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
KEYCHAIN_SERVICE="${KEYCHAIN_SERVICE:-Claude Code-credentials}"
KEYCHAIN_ACCOUNT="${KEYCHAIN_ACCOUNT:-$USER}"

DO_RESTART=0
for arg in "$@"; do
  case "$arg" in
    --restart) DO_RESTART=1 ;;
    -h|--help)
      grep -E '^# ' "$0" | sed 's/^# //; s/^#//'
      exit 0
      ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }

LOCAL_TMP=$(mktemp -t claude-creds.XXXXXX)
REMOTE_TMP="/tmp/$(basename "$LOCAL_TMP")"
trap 'rm -f "$LOCAL_TMP"; ssh "$SSH_HOST" "sudo rm -f $REMOTE_TMP" 2>/dev/null || true' EXIT

[[ "$(uname -s)" == "Darwin" ]] || { echo "ERROR: must run on macOS (uses Keychain)." >&2; exit 1; }

log "Extracting OAuth creds from Keychain (service=\"$KEYCHAIN_SERVICE\" account=\"$KEYCHAIN_ACCOUNT\")"
if ! security find-generic-password -s "$KEYCHAIN_SERVICE" -a "$KEYCHAIN_ACCOUNT" -w > "$LOCAL_TMP" 2>/dev/null; then
  echo "ERROR: Keychain entry not found." >&2
  echo "       Run 'claude /login' on this Mac first, then rerun this script." >&2
  exit 1
fi

# Sanity check the extracted JSON: must have a refreshToken, parsable shape.
python3 - "$LOCAL_TMP" <<'PY'
import json, sys, time
with open(sys.argv[1]) as f:
    d = json.load(f)
oauth = d.get("claudeAiOauth", {})
if not oauth.get("refreshToken"):
    print("ERROR: extracted credentials missing refreshToken", file=sys.stderr)
    sys.exit(1)
exp_ms = oauth.get("expiresAt", 0)
ttl_s = int(exp_ms / 1000 - time.time()) if exp_ms > 1e10 else None
print(f"   subscription={oauth.get('subscriptionType')}, "
      f"refresh_token={oauth['refreshToken'][:8]}..., "
      f"access_token_ttl={ttl_s}s")
PY

log "Uploading to $SSH_HOST:$REMOTE_TMP"
scp -q "$LOCAL_TMP" "$SSH_HOST:$REMOTE_TMP"

log "Pushing into container + fixing perms (preserving previous as .stale-bak)"
ssh "$SSH_HOST" "
  set -e
  sudo docker exec '$CONTAINER' cp /root/.claude/.credentials.json /root/.claude/.credentials.json.stale-bak 2>/dev/null || true
  sudo docker cp '$REMOTE_TMP' '$CONTAINER':/root/.claude/.credentials.json
  sudo docker exec '$CONTAINER' chown root:root /root/.claude/.credentials.json
  sudo docker exec '$CONTAINER' chmod 600 /root/.claude/.credentials.json
"

log "Verifying inside container"
ssh "$SSH_HOST" "sudo docker exec '$CONTAINER' python3 -c \"
import json, time
with open('/root/.claude/.credentials.json') as f:
    d = json.load(f)
o = d['claudeAiOauth']
print('   refresh_token:', o['refreshToken'][:8] + '...')
print('   subscription:', o.get('subscriptionType'))
print('   access_token_ttl:', int(o['expiresAt']/1000 - time.time()), 's')
\""

log "Sanity-checking that the API-key bypass is still in place"
KEY_STATE=$(ssh "$SSH_HOST" "sudo docker exec '$CONTAINER' sh -c 'printf %s \"\${ANTHROPIC_API_KEY:-}\"'")
if [[ -n "$KEY_STATE" ]]; then
  warn "ANTHROPIC_API_KEY is set inside the container — claude will prefer it over OAuth"
  warn "and bill the API key at full Opus rates. Blank it in $COMPOSE_DIR/.env and restart:"
  warn "    ssh $SSH_HOST 'sudo sed -i \"s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=|\" $COMPOSE_DIR/.env'"
  warn "    ssh $SSH_HOST 'cd $COMPOSE_DIR && sudo docker compose -f $COMPOSE_FILE up -d'"
else
  log "   ANTHROPIC_API_KEY is empty inside container — OAuth will be used."
fi

if [[ "$DO_RESTART" -eq 1 ]]; then
  log "Restarting container (--restart was passed)"
  ssh "$SSH_HOST" "cd '$COMPOSE_DIR' && sudo docker compose -f '$COMPOSE_FILE' restart hyperdraft"
  log "Restarted. Auto-spawned matches will pick up the fresh creds."
else
  log "Done. New match-spawns will pick up the fresh creds automatically."
  log "Pass --restart to recycle any in-flight 401-ing subprocesses."
fi

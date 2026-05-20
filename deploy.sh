#!/usr/bin/env bash
# Hyperdraft production deploy: rsync source to ovh2 and (re)build/start
# the docker-compose service. Replaces the previous systemd-based deploy;
# the one-shot ``scripts/deploy/migrate_off_systemd.sh`` handles the cutover.
#
# Card art and SCP art are NOT rsync'd here — they're hydrated separately via
# Git LFS using ``make seed-art`` (one-time or when art changes). The compose
# file bind-mounts /opt/hyperdraft/assets/card_art and
# /opt/hyperdraft/frontend/public/scp-art into the container.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_HOST="${DEPLOY_SSH_HOST:-ovh2}"
REMOTE_DIR="${DEPLOY_REMOTE_PATH:-/opt/hyperdraft}"
SITE_NAME="hyperdraft.discordwell.com"
REBOOT_SCRIPT="${HOME}/Projects/shared/reboot-vps.sh"

# SSH connection pooling — one master, persist 60s past last child.
CONTROL_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hyperdraft-deploy-ssh.XXXXXX")"
CONTROL_PATH="${CONTROL_DIR}/control"
SSH=(ssh -o ControlMaster=auto -o ControlPath="${CONTROL_PATH}" -o ControlPersist=60)
SCP=(scp -o ControlMaster=auto -o ControlPath="${CONTROL_PATH}" -o ControlPersist=60)
RSYNC_SSH="ssh -o ControlMaster=auto -o ControlPath=${CONTROL_PATH} -o ControlPersist=60"

cleanup() {
  "${SSH[@]}" -O exit "${SSH_HOST}" >/dev/null 2>&1 || true
  rm -rf "${CONTROL_DIR}"
}
trap cleanup EXIT

# --- Step 0: SSH kicker (reboot via OVH API if unreachable) ---
ensure_ssh() {
  if "${SSH[@]}" -o ConnectTimeout=10 -o BatchMode=yes "$SSH_HOST" "true" 2>/dev/null; then
    return 0
  fi
  echo ">> SSH unreachable — kicking server via OVH API..."
  if [[ -x "$REBOOT_SCRIPT" ]]; then
    "$REBOOT_SCRIPT" ovh2 --wait
  else
    echo "ERROR: reboot script not found: $REBOOT_SCRIPT" >&2
    exit 1
  fi
}

echo "=== Hyperdraft Deploy to ${SSH_HOST} ==="
ensure_ssh

# --- Step 1: pre-deploy gate — refuse mid-game wipes ---
#
# session_manager.sessions is in-memory; ``docker compose up -d --build``
# replaces the container and wipes every running match. Query the existing
# server for live Ultra matches; abort unless --force is passed.
echo ">> [1/6] Pre-deploy gate (checking for in-flight ultra matches)..."
FORCE_DEPLOY="${FORCE_DEPLOY:-0}"
# The /ultra-pending endpoint is localhost-gated (Phase 2.4) so we call it
# from INSIDE the container — a host-side curl through docker's port-forward
# sees the docker bridge gateway as the source IP, not 127.0.0.1, and would
# get a 404. If the container isn't running yet (first deploy), there's
# nothing to gate on; the fallback returns "pending: []".
PENDING_JSON="$("${SSH[@]}" "$SSH_HOST" \
  "docker exec hyperdraft-hyperdraft-1 curl -fsS --max-time 5 http://127.0.0.1:8030/api/match/ultra-pending 2>/dev/null || echo '{\"pending\": []}'")"
PENDING_COUNT="$(printf '%s' "$PENDING_JSON" | python3 -c 'import json,sys;print(len(json.load(sys.stdin).get("pending",[])))' 2>/dev/null || echo 0)"
if [ "${PENDING_COUNT:-0}" -gt 0 ]; then
  echo "  WARN: ${PENDING_COUNT} ultra match(es) currently in-flight."
  if [ "$FORCE_DEPLOY" != "1" ]; then
    echo "  Re-run with FORCE_DEPLOY=1 to proceed anyway (this WILL drop running games)."
    exit 1
  fi
  echo "  FORCE_DEPLOY=1 — proceeding."
fi

# --- Step 2: ensure host directory + ownership ---
echo ">> [2/6] Ensuring ${SSH_HOST}:${REMOTE_DIR} exists..."
"${SSH[@]}" "$SSH_HOST" "sudo mkdir -p $REMOTE_DIR && sudo chown ubuntu:ubuntu $REMOTE_DIR"

# --- Step 3: rsync source (excludes art; bind-mounted into container) ---
#
# Exclusions mirror .dockerignore so the build context inside the container
# matches what gets shipped. Art directories are deliberately NOT rsync'd:
# the host hydrates them via ``make seed-art`` (Git LFS pull from R2).
echo ">> [3/6] Syncing source to ${SSH_HOST}:${REMOTE_DIR}..."
rsync -az --delete \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='venv/' \
  --exclude='node_modules/' \
  --exclude='frontend/node_modules/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache/' \
  --exclude='.mypy_cache/' \
  --exclude='.ruff_cache/' \
  --exclude='frontend/dist/' \
  --exclude='claudepad.md' \
  --exclude='oldpad.md' \
  --exclude='.claude/' \
  --exclude='logs/' \
  --exclude='storage/' \
  --exclude='art-runs/' \
  --exclude='data/raw/' \
  --exclude='codex-pokemon-strategy/scratch/' \
  --exclude='.env' \
  --exclude='.env.local' \
  --exclude='.DS_Store' \
  --exclude='assets/card_art/' \
  --exclude='frontend/public/scp-art/' \
  -e "${RSYNC_SSH}" \
  "${SCRIPT_DIR}/" \
  "${SSH_HOST}:${REMOTE_DIR}/"

# --- Step 4: verify art has been seeded ---
#
# The container's bind mounts will fail to find files if these directories
# don't exist on the host. ``make seed-art`` is the one-time hydration step;
# we just warn here rather than refuse, so the operator can deploy code-only
# changes even if art is mid-sync.
echo ">> [4/6] Verifying art hydration..."
ART_STATUS="$("${SSH[@]}" "$SSH_HOST" "
  card_art_count=\$(find ${REMOTE_DIR}/assets/card_art -type f -name '*.png' 2>/dev/null | head -10 | wc -l || echo 0)
  scp_art_count=\$(find ${REMOTE_DIR}/frontend/public/scp-art -type f -name '*.png' 2>/dev/null | head -10 | wc -l || echo 0)
  echo \"card_art=\${card_art_count} scp_art=\${scp_art_count}\"
")"
echo "  ${ART_STATUS}"
if printf '%s' "$ART_STATUS" | grep -q 'card_art=0\|scp_art=0'; then
  echo "  WARN: art directory empty or missing. Run 'make seed-art' to hydrate."
fi

# --- Step 5: migrate off systemd (one-shot, idempotent), then docker compose ---
echo ">> [5/6] Migrating off systemd (no-op if already migrated)..."
"${SSH[@]}" "$SSH_HOST" "cd $REMOTE_DIR && bash scripts/deploy/migrate_off_systemd.sh"

echo ">> Building and (re)starting docker compose..."
# --pull is omitted to keep base layer cached between deploys; rebuild from scratch with
# DOCKER_BUILD_FRESH=1 if a new base image is desired.
BUILD_FLAGS=""
if [ "${DOCKER_BUILD_FRESH:-0}" = "1" ]; then
  BUILD_FLAGS="--pull"
fi
"${SSH[@]}" "$SSH_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml -p hyperdraft up -d --build ${BUILD_FLAGS}"

# --- Step 6: Caddy reload + health check ---
echo ">> [6/6] Updating Caddy site and reloading..."
"${SCP[@]}" -q "${SCRIPT_DIR}/caddy.conf" "${SSH_HOST}:/tmp/${SITE_NAME}"
"${SSH[@]}" "$SSH_HOST" "sudo mv /tmp/${SITE_NAME} /etc/caddy/sites/${SITE_NAME} && sudo systemctl reload caddy"

echo ">> Waiting for service to start..."
sleep 5
STATUS="$("${SSH[@]}" "$SSH_HOST" "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8030/api/health")"
if [ "$STATUS" = "200" ]; then
  echo "=== Deploy successful! ==="
  echo "URL: https://${SITE_NAME}"
else
  echo "WARNING: Health check returned $STATUS"
  echo "--- last 80 lines of container logs ---"
  "${SSH[@]}" "$SSH_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml -p hyperdraft logs --tail=80 hyperdraft"
  exit 1
fi

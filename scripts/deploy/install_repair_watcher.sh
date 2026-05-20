#!/usr/bin/env bash
# Install the host-side hyperdraft-repair-watcher systemd timer.
# Idempotent. Runs on the host (ovh2), NOT inside the container.
#
# Prereqs:
#   - /etc/hyperdraft/github-pat exists (mode 0400, root-owned) — a
#     fine-grained PAT with contents:write + pull-requests:write on
#     discordwell/Hyperdraft. The watcher reads it to push branches +
#     open draft PRs.
#   - gh CLI installed on the host (apt install gh / brew install gh).
#
# Without those, the watcher still runs, saves patches under
# storage/repair/<session>/patch.diff, but does not push to GitHub.

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/hyperdraft}"
SCRIPT_NAME="repair_patch_watcher.sh"
SCRIPT_PATH="${REPO_DIR}/scripts/ops/${SCRIPT_NAME}"

UNIT_NAME="hyperdraft-repair-watcher"
SERVICE_PATH="/etc/systemd/system/${UNIT_NAME}.service"
TIMER_PATH="/etc/systemd/system/${UNIT_NAME}.timer"

if [[ ! -x "$SCRIPT_PATH" ]]; then
  echo "ERROR: watcher script not executable at $SCRIPT_PATH" >&2
  exit 1
fi

echo ">> Installing ${UNIT_NAME} systemd timer..."

sudo tee "$SERVICE_PATH" > /dev/null <<UNIT
[Unit]
Description=Hyperdraft auto-repair patch watcher
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/env bash $SCRIPT_PATH
StandardOutput=journal
StandardError=journal
User=root

[Install]
WantedBy=multi-user.target
UNIT

sudo tee "$TIMER_PATH" > /dev/null <<UNIT
[Unit]
Description=Run hyperdraft-repair-watcher every 60s
Requires=${UNIT_NAME}.service

[Timer]
OnBootSec=120
OnUnitActiveSec=60s
AccuracySec=10s

[Install]
WantedBy=timers.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now "${UNIT_NAME}.timer"

echo ">> Installed. Logs: sudo journalctl -u ${UNIT_NAME} -f"
echo ">> Status:        sudo systemctl status ${UNIT_NAME}.timer"

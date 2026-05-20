#!/usr/bin/env bash
# One-shot migration from the systemd-unit deploy to docker-compose.
# Idempotent: safe to run any number of times. Called from deploy.sh on every
# deploy; the second-and-later runs are no-ops.
#
# What it does:
#   - stop + disable the legacy hyperdraft.service unit if still installed
#   - remove the unit file
#   - reload systemd

set -euo pipefail

UNIT_NAME="hyperdraft.service"
UNIT_PATH="/etc/systemd/system/${UNIT_NAME}"

if ! systemctl list-unit-files 2>/dev/null | grep -q "^${UNIT_NAME}"; then
  if [ ! -f "${UNIT_PATH}" ]; then
    echo "  (no legacy ${UNIT_NAME} found — nothing to migrate)"
    exit 0
  fi
fi

echo "  -> stopping legacy ${UNIT_NAME}"
sudo systemctl stop "${UNIT_NAME}" 2>/dev/null || true

echo "  -> disabling legacy ${UNIT_NAME}"
sudo systemctl disable "${UNIT_NAME}" 2>/dev/null || true

if [ -f "${UNIT_PATH}" ]; then
  echo "  -> removing ${UNIT_PATH}"
  sudo rm -f "${UNIT_PATH}"
fi

sudo systemctl daemon-reload

echo "  -> systemd migration complete"

#!/usr/bin/env bash
set -euo pipefail

SSH_KEY=~/.ssh/ovh2_vps
HOST=ubuntu@15.204.59.61
REMOTE_DIR=/opt/hyperdraft
SERVICE=hyperdraft

echo "=== Hyperdraft Deploy to ovh2 ==="

# 1. Build frontend
echo "[1/5] Building frontend..."
cd "$(dirname "$0")/frontend"
npm run build --silent
cd ..

# 2. Rsync project (exclude node_modules, __pycache__, .git, venv)
echo "[2/5] Syncing files to $HOST:$REMOTE_DIR..."
ssh -i "$SSH_KEY" "$HOST" "sudo mkdir -p $REMOTE_DIR && sudo chown ubuntu:ubuntu $REMOTE_DIR"
rsync -az --delete \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='venv' \
  --exclude='.mypy_cache' \
  --exclude='.pytest_cache' \
  --exclude='*.pyc' \
  --exclude='oldpad.md' \
  --exclude='claudepad.md' \
  -e "ssh -i $SSH_KEY" \
  . "$HOST:$REMOTE_DIR/"

# 3. Set up Python venv and install deps
echo "[3/5] Installing Python dependencies..."
ssh -i "$SSH_KEY" "$HOST" "cd $REMOTE_DIR && \
  ([ -f venv/bin/pip ] || python3 -m venv venv) && \
  venv/bin/pip install -q -r requirements-server.txt"

# 4. Install/update systemd service
echo "[4/5] Setting up systemd service..."
ssh -i "$SSH_KEY" "$HOST" "sudo tee /etc/systemd/system/$SERVICE.service > /dev/null << 'UNIT'
[Unit]
Description=Hyperdraft Game Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$REMOTE_DIR
ExecStart=$REMOTE_DIR/venv/bin/uvicorn src.server.main:socket_app --host 127.0.0.1 --port 8030
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE
sudo systemctl restart $SERVICE"

# 5. Deploy Caddy config
echo "[5/5] Updating Caddy config..."
scp -i "$SSH_KEY" caddy.conf "$HOST:/tmp/hyperdraft.discordwell.com"
ssh -i "$SSH_KEY" "$HOST" "sudo mv /tmp/hyperdraft.discordwell.com /etc/caddy/sites/hyperdraft.discordwell.com && sudo systemctl reload caddy"

# Health check
echo "Waiting for service to start..."
sleep 3
STATUS=$(ssh -i "$SSH_KEY" "$HOST" "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8030/api/health")
if [ "$STATUS" = "200" ]; then
  echo "=== Deploy successful! ==="
  echo "https://hyperdraft.discordwell.com"
else
  echo "WARNING: Health check returned $STATUS"
  ssh -i "$SSH_KEY" "$HOST" "sudo journalctl -u $SERVICE --since '30 seconds ago' --no-pager -n 20"
fi

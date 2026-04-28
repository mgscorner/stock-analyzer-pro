#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/stock-analyzer"
RELEASES_DIR="$APP_ROOT/releases"
ENV_DIR="$APP_ROOT/env"
LOG_DIR="$APP_ROOT/logs"
CURRENT_LINK="$APP_ROOT/current"
VENV_DIR="$APP_ROOT/venv"
WORKER_SERVICE_DST="/etc/systemd/system/stock-analyzer-worker.service"
SCHEDULER_SERVICE_DST="/etc/systemd/system/stock-analyzer-scheduler.service"
FIREWALL_SCRIPT="/usr/local/bin/stock-analyzer-firewall.sh"
FIREWALL_SERVICE="/etc/systemd/system/stock-analyzer-firewall.service"

echo "Installing base packages..."
sudo apt update
sudo apt install -y python3 python3-venv python3-pip unzip curl git nginx certbot python3-certbot-nginx

echo "Creating runtime directories..."
sudo mkdir -p "$RELEASES_DIR" "$ENV_DIR" "$LOG_DIR"
sudo chown -R "$USER:$USER" "$APP_ROOT"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating shared Python virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

echo "Installing systemd unit files..."
sudo tee "$WORKER_SERVICE_DST" > /dev/null <<'EOF'
[Unit]
Description=Stock Analyzer Worker API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/stock-analyzer/current/worker
EnvironmentFile=/opt/stock-analyzer/env/worker.env
ExecStart=/opt/stock-analyzer/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee "$SCHEDULER_SERVICE_DST" > /dev/null <<'EOF'
[Unit]
Description=Stock Analyzer Background Scheduler
After=network.target stock-analyzer-worker.service
Requires=stock-analyzer-worker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/stock-analyzer/current/worker
EnvironmentFile=/opt/stock-analyzer/env/worker.env
ExecStart=/opt/stock-analyzer/venv/bin/python run_scheduler.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable stock-analyzer-worker
sudo systemctl enable stock-analyzer-scheduler
sudo systemctl enable nginx

echo "Installing firewall allow rules for HTTP/HTTPS..."
sudo tee "$FIREWALL_SCRIPT" > /dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || iptables -I INPUT 4 -p tcp --dport 80 -j ACCEPT
iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || iptables -I INPUT 5 -p tcp --dport 443 -j ACCEPT
EOF
sudo chmod +x "$FIREWALL_SCRIPT"

sudo tee "$FIREWALL_SERVICE" > /dev/null <<'EOF'
[Unit]
Description=Stock Analyzer Firewall Rules
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/stock-analyzer-firewall.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable stock-analyzer-firewall.service
sudo systemctl restart stock-analyzer-firewall.service

echo
echo "VM bootstrap complete."
echo "Next steps:"
echo "  1. create $ENV_DIR/worker.env"
echo "  2. upload a release zip"
echo "  3. run deployment/scripts/deploy_release.sh <zip> <domain-or-ip> [letsencrypt-email]"
echo
echo "Expected stable paths:"
echo "  releases: $RELEASES_DIR"
echo "  current:  $CURRENT_LINK"
echo "  env:      $ENV_DIR/worker.env"

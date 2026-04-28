#!/usr/bin/env bash
set -euo pipefail

ZIP_PATH="${1:-}"
PUBLIC_HOST="${2:-}"
LETSENCRYPT_EMAIL="${3:-}"

APP_ROOT="/opt/stock-analyzer"
RELEASES_DIR="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"
ENV_FILE="$APP_ROOT/env/worker.env"
VENV_DIR="$APP_ROOT/venv"
NGINX_SITE="/etc/nginx/sites-available/stock-analyzer"
NGINX_ENABLED="/etc/nginx/sites-enabled/stock-analyzer"

usage() {
  echo "Usage: bash deployment/scripts/deploy_release.sh <release-zip> <domain-or-ip> [letsencrypt-email]"
}

is_ip_address() {
  [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
}

if [[ -z "$ZIP_PATH" || -z "$PUBLIC_HOST" ]]; then
  usage
  exit 1
fi

if [[ ! -f "$ZIP_PATH" ]]; then
  echo "Release zip not found: $ZIP_PATH"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE"
  exit 1
fi

mkdir -p "$RELEASES_DIR"

RELEASE_NAME="$(basename "$ZIP_PATH" .zip)"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_NAME"
TMP_DIR="$(mktemp -d)"

cleanup() {
  chmod -R u+rwX "$TMP_DIR" 2>/dev/null || true
  rm -rf "$TMP_DIR" 2>/dev/null || true
}
trap cleanup EXIT

echo "Unpacking release $RELEASE_NAME..."
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"
set +e
unzip -q "$ZIP_PATH" -d "$TMP_DIR"
UNZIP_STATUS=$?
set -e
if [[ "$UNZIP_STATUS" -gt 1 ]]; then
  echo "Unzip failed with exit code $UNZIP_STATUS"
  exit "$UNZIP_STATUS"
fi
chmod -R u+rwX "$TMP_DIR" 2>/dev/null || true

if [[ ! -d "$TMP_DIR/$RELEASE_NAME/production_app" ]]; then
  echo "Release archive does not contain expected production_app folder."
  exit 1
fi

chmod -R u+rwX "$TMP_DIR/$RELEASE_NAME/production_app" 2>/dev/null || true
mv "$TMP_DIR/$RELEASE_NAME/production_app" "$RELEASE_DIR/"
chown -R "$USER:$USER" "$RELEASE_DIR"

NEW_APP_DIR="$RELEASE_DIR/production_app"

echo "Installing Python dependencies..."
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$NEW_APP_DIR/worker/requirements.txt"

echo "Switching current release..."
ln -sfn "$NEW_APP_DIR" "$CURRENT_LINK"

echo "Writing nginx site config..."
sudo tee "$NGINX_SITE" > /dev/null <<EOF
server {
    listen 80;
    server_name $PUBLIC_HOST;

    root $CURRENT_LINK/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        try_files \$uri /index.html;
    }
}
EOF

sudo ln -sf "$NGINX_SITE" "$NGINX_ENABLED"
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t

echo "Restarting services..."
sudo systemctl restart stock-analyzer-worker
sudo systemctl restart stock-analyzer-scheduler
sudo systemctl restart nginx

echo "Running smoke test..."
bash "$CURRENT_LINK/deployment/scripts/smoke_test.sh" "$PUBLIC_HOST"

if [[ -n "$LETSENCRYPT_EMAIL" ]] && ! is_ip_address "$PUBLIC_HOST"; then
  echo "Requesting/refreshing TLS certificate..."
  set +e
  sudo certbot --nginx --non-interactive --agree-tos -m "$LETSENCRYPT_EMAIL" -d "$PUBLIC_HOST" --redirect
  CERTBOT_STATUS=$?
  set -e
  if [[ "$CERTBOT_STATUS" -eq 0 ]]; then
    sudo systemctl reload nginx
  else
    echo "WARNING: TLS setup failed. The application is still deployed over HTTP."
    echo "Retry later with:"
    echo "  sudo certbot --nginx --non-interactive --agree-tos -m $LETSENCRYPT_EMAIL -d $PUBLIC_HOST --redirect"
  fi
else
  if is_ip_address "$PUBLIC_HOST"; then
    echo "Public host is an IP address. Skipping Let's Encrypt TLS."
  else
    echo "No Let's Encrypt email provided. Skipping TLS."
  fi
fi

echo
echo "Release deployed successfully."
echo "Current release: $NEW_APP_DIR"
echo "Public host: $PUBLIC_HOST"
echo "Rollback command:"
echo "  bash $CURRENT_LINK/deployment/scripts/rollback_release.sh"

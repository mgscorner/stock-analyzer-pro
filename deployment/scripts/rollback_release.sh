#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/stock-analyzer"
RELEASES_DIR="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"

if [[ ! -L "$CURRENT_LINK" ]]; then
  echo "Current symlink not found: $CURRENT_LINK"
  exit 1
fi

CURRENT_TARGET="$(readlink -f "$CURRENT_LINK")"

mapfile -t RELEASE_DIRS < <(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d | sort)

PREVIOUS_RELEASE=""
for dir in "${RELEASE_DIRS[@]}"; do
  APP_DIR="$dir/production_app"
  if [[ "$APP_DIR" == "$CURRENT_TARGET" ]]; then
    break
  fi
  PREVIOUS_RELEASE="$APP_DIR"
done

if [[ -z "$PREVIOUS_RELEASE" ]]; then
  echo "No previous release available."
  exit 1
fi

echo "Rolling back to: $PREVIOUS_RELEASE"
ln -sfn "$PREVIOUS_RELEASE" "$CURRENT_LINK"
sudo systemctl restart stock-analyzer-worker
sudo systemctl restart stock-analyzer-scheduler
sudo systemctl restart nginx

echo "Rollback complete."

#!/usr/bin/env bash
set -euo pipefail

PUBLIC_HOST="${1:-127.0.0.1}"

wait_for_url() {
  local url="$1"
  local attempts="${2:-20}"
  local delay="${3:-2}"
  local i
  for ((i=1; i<=attempts; i++)); do
    if curl --fail --silent "$url" > /dev/null; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

echo "Checking systemd services..."
systemctl is-active --quiet stock-analyzer-worker
systemctl is-active --quiet stock-analyzer-scheduler
systemctl is-active --quiet nginx

echo "Checking worker health..."
wait_for_url "http://127.0.0.1:8000/health"

echo "Checking frontend locally..."
wait_for_url "http://127.0.0.1/"

echo "Checking nginx /api health..."
wait_for_url "http://127.0.0.1/api/health"

echo "Smoke test passed for $PUBLIC_HOST."

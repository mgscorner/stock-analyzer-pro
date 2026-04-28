#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "oracle_bootstrap.sh is deprecated."
echo "Use these instead:"
echo "  bash $SCRIPT_DIR/bootstrap_vm.sh"
echo "  bash $SCRIPT_DIR/deploy_release.sh <release-zip> <domain-or-ip> [letsencrypt-email]"
exit 1

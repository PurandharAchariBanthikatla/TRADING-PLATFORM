#!/usr/bin/env bash
# Shared constants and helpers sourced by the other scripts/*.sh files.
# Not meant to be run directly.

set -euo pipefail

NETWORK_NAME="exchange-net"
PG_VOLUME="exchange-pg-data"
PG_CONTAINER="exchange-postgres"
REDIS_CONTAINER="exchange-redis"
GATEWAY_CONTAINER="exchange-api-gateway"
LEDGER_CONTAINER="exchange-ledger-service"
WALLET_CONTAINER="exchange-wallet-service"
MARKETDATA_CONTAINER="exchange-market-data-service"
FRONTEND_CONTAINER="exchange-frontend"

PG_IMAGE="postgres:16.6-bookworm"
REDIS_IMAGE="redis:7.4.1-bookworm"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

log() { echo "[docker] $*"; }

require_env_file() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE}. Copy .env.example to .env at the repo root and fill in real secrets first." >&2
    exit 1
  fi
}

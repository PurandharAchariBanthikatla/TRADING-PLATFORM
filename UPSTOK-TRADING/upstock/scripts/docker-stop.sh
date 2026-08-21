#!/usr/bin/env bash
# Stops all stack containers. Pass --clean to also remove the network and
# the Postgres data volume (destructive -- wipes local data).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

for container in "${FRONTEND_CONTAINER}" "${GATEWAY_CONTAINER}" "${MARKETDATA_CONTAINER}" "${WALLET_CONTAINER}" "${LEDGER_CONTAINER}" "${REDIS_CONTAINER}" "${PG_CONTAINER}"; do
  if docker inspect "${container}" >/dev/null 2>&1; then
    log "Stopping and removing ${container}"
    docker rm -f "${container}" >/dev/null
  fi
done

if [[ "${1:-}" == "--clean" ]]; then
  log "Removing network ${NETWORK_NAME} and volume ${PG_VOLUME}"
  docker network rm "${NETWORK_NAME}" >/dev/null 2>&1 || true
  docker volume rm "${PG_VOLUME}" >/dev/null 2>&1 || true
fi

log "Stack stopped."

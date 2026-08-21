#!/usr/bin/env bash
# Runs the whole stack with plain `docker network create` / `docker volume
# create` / `docker run` -- no Compose, per project constraints. Internal
# services (Postgres, Redis) are attached to the network but NOT published
# to the host, matching how they'd sit in staging/production; only the
# frontend and API gateway get host-published ports.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_env_file

TAG="${1:-latest}"

log "Ensuring network ${NETWORK_NAME} exists"
docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1 || docker network create "${NETWORK_NAME}"

log "Ensuring volume ${PG_VOLUME} exists"
docker volume inspect "${PG_VOLUME}" >/dev/null 2>&1 || docker volume create "${PG_VOLUME}"

# --- Postgres (internal only) ---
if ! docker inspect "${PG_CONTAINER}" >/dev/null 2>&1; then
  log "Starting ${PG_CONTAINER}"
  docker run -d \
    --name "${PG_CONTAINER}" \
    --network "${NETWORK_NAME}" \
    --restart unless-stopped \
    -v "${PG_VOLUME}:/var/lib/postgresql/data" \
    -e POSTGRES_USER=exchange \
    -e POSTGRES_PASSWORD=exchange \
    -e POSTGRES_DB=exchange \
    --health-cmd="pg_isready -U exchange" \
    --health-interval=5s --health-timeout=3s --health-retries=10 \
    "${PG_IMAGE}"
else
  log "${PG_CONTAINER} already running"
fi

# --- Redis (internal only) ---
if ! docker inspect "${REDIS_CONTAINER}" >/dev/null 2>&1; then
  log "Starting ${REDIS_CONTAINER}"
  docker run -d \
    --name "${REDIS_CONTAINER}" \
    --network "${NETWORK_NAME}" \
    --restart unless-stopped \
    --health-cmd="redis-cli ping" \
    --health-interval=5s --health-timeout=3s --health-retries=10 \
    "${REDIS_IMAGE}"
else
  log "${REDIS_CONTAINER} already running"
fi

log "Waiting for Postgres and Redis to report healthy..."
for container in "${PG_CONTAINER}" "${REDIS_CONTAINER}"; do
  for _ in $(seq 1 30); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "${container}")"
    [[ "${status}" == "healthy" ]] && break
    sleep 2
  done
done

# --- Migrations (one-off container, runs to completion then exits) ---
log "Running database migrations"
docker run --rm \
  --network "${NETWORK_NAME}" \
  --env-file "${ENV_FILE}" \
  -e DATABASE_URL="postgresql+asyncpg://exchange:exchange@${PG_CONTAINER}:5432/exchange" \
  --entrypoint alembic \
  "exchange/api-gateway:${TAG}" \
  upgrade head

# --- API gateway (published on host:8000) ---
docker rm -f "${GATEWAY_CONTAINER}" >/dev/null 2>&1 || true
log "Starting ${GATEWAY_CONTAINER}"
docker run -d \
  --name "${GATEWAY_CONTAINER}" \
  --network "${NETWORK_NAME}" \
  --restart unless-stopped \
  --env-file "${ENV_FILE}" \
  -e DATABASE_URL="postgresql+asyncpg://exchange:exchange@${PG_CONTAINER}:5432/exchange" \
  -e REDIS_URL="redis://${REDIS_CONTAINER}:6379/0" \
  -p 8000:8000 \
  "exchange/api-gateway:${TAG}"

# --- Ledger service migrations (one-off container, runs to completion) ---
log "Running ledger-service database migrations"
docker run --rm \
  --network "${NETWORK_NAME}" \
  --env-file "${ENV_FILE}" \
  -e DATABASE_URL="postgresql+asyncpg://exchange:exchange@${PG_CONTAINER}:5432/exchange" \
  --entrypoint alembic \
  "exchange/ledger-service:${TAG}" \
  upgrade head

# --- Ledger service (internal only -- not published to the host; only
# api-gateway and other backend services reach it over exchange-net) ---
docker rm -f "${LEDGER_CONTAINER}" >/dev/null 2>&1 || true
log "Starting ${LEDGER_CONTAINER}"
docker run -d \
  --name "${LEDGER_CONTAINER}" \
  --network "${NETWORK_NAME}" \
  --restart unless-stopped \
  --env-file "${ENV_FILE}" \
  -e SERVICE_NAME=ledger-service \
  -e DATABASE_URL="postgresql+asyncpg://exchange:exchange@${PG_CONTAINER}:5432/exchange" \
  "exchange/ledger-service:${TAG}"

# --- Wallet service migrations (one-off container, runs to completion) ---
log "Running wallet-service database migrations"
docker run --rm \
  --network "${NETWORK_NAME}" \
  --env-file "${ENV_FILE}" \
  -e DATABASE_URL="postgresql+asyncpg://exchange:exchange@${PG_CONTAINER}:5432/exchange" \
  --entrypoint alembic \
  "exchange/wallet-service:${TAG}" \
  upgrade head

# --- Wallet service (internal only -- calls ledger-service over
# exchange-net using LEDGER_SERVICE_BASE_URL / INTERNAL_SERVICE_KEY) ---
docker rm -f "${WALLET_CONTAINER}" >/dev/null 2>&1 || true
log "Starting ${WALLET_CONTAINER}"
docker run -d \
  --name "${WALLET_CONTAINER}" \
  --network "${NETWORK_NAME}" \
  --restart unless-stopped \
  --env-file "${ENV_FILE}" \
  -e SERVICE_NAME=wallet-service \
  -e DATABASE_URL="postgresql+asyncpg://exchange:exchange@${PG_CONTAINER}:5432/exchange" \
  -e LEDGER_SERVICE_BASE_URL="http://${LEDGER_CONTAINER}:8000/api/v1" \
  "exchange/wallet-service:${TAG}"

# --- Market-data service migrations (one-off container, runs to completion) ---
log "Running market-data-service database migrations"
docker run --rm \
  --network "${NETWORK_NAME}" \
  --env-file "${ENV_FILE}" \
  -e DATABASE_URL="postgresql+asyncpg://exchange:exchange@${PG_CONTAINER}:5432/exchange" \
  --entrypoint alembic \
  "exchange/market-data-service:${TAG}" \
  upgrade head

# --- Market-data service (internal only -- runs its own background
# simulator/candle-aggregator/DLQ-maintenance loops in-process, publishing
# to and consuming from Redis Streams on REDIS_URL) ---
docker rm -f "${MARKETDATA_CONTAINER}" >/dev/null 2>&1 || true
log "Starting ${MARKETDATA_CONTAINER}"
docker run -d \
  --name "${MARKETDATA_CONTAINER}" \
  --network "${NETWORK_NAME}" \
  --restart unless-stopped \
  --env-file "${ENV_FILE}" \
  -e SERVICE_NAME=market-data-service \
  -e DATABASE_URL="postgresql+asyncpg://exchange:exchange@${PG_CONTAINER}:5432/exchange" \
  -e REDIS_URL="redis://${REDIS_CONTAINER}:6379/1" \
  "exchange/market-data-service:${TAG}"

# --- Frontend (published on host:3000) ---
docker rm -f "${FRONTEND_CONTAINER}" >/dev/null 2>&1 || true
log "Starting ${FRONTEND_CONTAINER}"
docker run -d \
  --name "${FRONTEND_CONTAINER}" \
  --network "${NETWORK_NAME}" \
  --restart unless-stopped \
  -e NEXT_PUBLIC_API_BASE_URL="http://localhost:8000/api/v1" \
  -p 3000:3000 \
  "exchange/frontend:${TAG}"

log "Up. Frontend: http://localhost:3000  Gateway: http://localhost:8000/docs"

#!/usr/bin/env bash
# Builds every service image locally, tagged with the current git SHA (falls
# back to "dev" outside a git repo / dirty tree). Mirrors the tagging scheme
# used by the CI/CD release pipeline (.github/workflows/cd.yml) so an image
# built here and one built by CI are byte-identical given the same commit.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

TAG="${1:-$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo dev)}"

log "Building exchange/api-gateway:${TAG}"
docker build -t "exchange/api-gateway:${TAG}" -t "exchange/api-gateway:latest" \
  "${ROOT_DIR}/services/api-gateway"

log "Building exchange/ledger-service:${TAG}"
docker build -t "exchange/ledger-service:${TAG}" -t "exchange/ledger-service:latest" \
  "${ROOT_DIR}/services/ledger-service"

log "Building exchange/wallet-service:${TAG}"
docker build -t "exchange/wallet-service:${TAG}" -t "exchange/wallet-service:latest" \
  "${ROOT_DIR}/services/wallet-service"

log "Building exchange/market-data-service:${TAG}"
docker build -t "exchange/market-data-service:${TAG}" -t "exchange/market-data-service:latest" \
  "${ROOT_DIR}/services/market-data-service"

log "Building exchange/frontend:${TAG}"
docker build -t "exchange/frontend:${TAG}" -t "exchange/frontend:latest" \
  "${ROOT_DIR}/frontend"

log "Done. Built images tagged ${TAG} and latest."

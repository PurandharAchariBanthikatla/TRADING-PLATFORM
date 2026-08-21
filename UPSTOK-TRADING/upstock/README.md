# Exchange (working name)

A sandbox-mode cryptocurrency trading platform, built incrementally as a
set of independently deployable services. **This repo does not yet hold real
customer funds anywhere, on purpose** -- see [Roadmap](#roadmap) below.

## What's actually built right now

This is phase 1 of a multi-phase build. Don't assume anything beyond this
list exists yet:

- **`services/api-gateway`** -- FastAPI service. Implements: user
  registration, login, JWT access/refresh tokens with rotation + reuse
  detection, logout, RBAC scaffolding (`user` / `admin` roles), Redis-backed
  rate limiting on auth endpoints, structured JSON logging, request-ID
  correlation, security response headers, `/health/live` + `/health/ready`,
  and a full pytest suite run against real Postgres + Redis in CI.
- **`frontend`** -- Next.js 14 (App Router) + TypeScript + Tailwind.
  Implements: landing page, register page, login page, and a dashboard
  placeholder behind an auth guard with silent token refresh.
- **Docker** -- multi-stage, non-root, pinned-version Dockerfiles for both
  services. **No Docker Compose is used anywhere in this project, by
  design** -- see `scripts/`.
- **CI/CD** -- GitHub Actions: `ci.yml` lints, type-checks, tests, and
  vulnerability-scans every PR and push to `main`; `cd.yml` builds
  SHA-tagged immutable images and deploys to staging then production
  (behind a required manual approval), once real staging/production hosts
  exist -- right now those deploy steps are clearly-marked placeholders.

## What's explicitly NOT built yet

Matching engine, order book, wallet/ledger service, risk engine, settlement
service, notification service, reporting service, WebSocket market-data
gateway, the trading terminal UI, the admin portal, MFA, and margin/futures
are all future phases. Nothing in this repo should be mistaken for a
functioning exchange yet -- it's the auth + infrastructure foundation
everything else gets built on.

## Repository layout

```
.
├── frontend/                # Next.js app
├── services/
│   └── api-gateway/         # FastAPI auth + gateway service
├── scripts/                 # docker-build.sh / docker-run.sh / docker-stop.sh (no Compose)
├── .github/workflows/       # ci.yml, cd.yml
└── docs/                    # architecture, setup, deployment notes
```

## Local setup

### Option A -- Docker (matches how it runs in staging/production)

```bash
cp .env.example .env                              # fill in a real JWT_SECRET_KEY
./scripts/docker-build.sh
./scripts/docker-run.sh
# Frontend:  http://localhost:3000
# API docs:  http://localhost:8000/docs
./scripts/docker-stop.sh            # stop everything
./scripts/docker-stop.sh --clean    # stop + remove network/volume (wipes local DB)
```

### Option B -- run services natively (faster iteration)

```bash
# Postgres + Redis, still via plain docker (no Compose):
docker network create exchange-net
docker run -d --name exchange-postgres --network exchange-net -p 5432:5432 \
  -e POSTGRES_USER=exchange -e POSTGRES_PASSWORD=exchange -e POSTGRES_DB=exchange \
  postgres:16.6-bookworm
docker run -d --name exchange-redis --network exchange-net -p 6379:6379 redis:7.4.1-bookworm

# API gateway
cd services/api-gateway
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

### Running tests

```bash
cd services/api-gateway
# requires the Postgres + Redis containers above (or CI's service containers)
pytest --cov=app --cov-report=term-missing
```

See [`docs/SETUP.md`](docs/SETUP.md) for a fuller walkthrough and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how this fits the
eventual full system.

## Environment variables

Each service documents its own variables in `<service>/.env.example`. The
root `.env.example` is what `scripts/docker-run.sh` reads. Never commit a
real `.env` file -- `.gitignore` excludes them, but review diffs anyway.

## Roadmap

1. ~~Foundation: repo structure, Docker (no Compose), Postgres, CI/CD~~
2. ~~Authentication: register / login / refresh / logout, RBAC scaffold~~
3. Ledger + wallet service: double-entry accounting core, deposits/withdrawals (paper funds only)
4. Spot matching engine: price-time priority, partial fills, cancellations
5. Trading UI + WebSocket market-data gateway: order book, terminal, live updates
6. Risk engine: balance/limit checks, rate limits
7. Admin portal: users, KYC, assets, markets, orders, risk controls, audit logs
8. Observability: Prometheus metrics, tracing, dashboards, alerting
9. Margin/futures (only after spot is stable and verified end-to-end)
10. Real-fund readiness review (security, reconciliation, compliance sign-off)

Each phase is built as a complete vertical slice -- UI through to database
-- and tested before the next one starts, per the project's own ground
rules.

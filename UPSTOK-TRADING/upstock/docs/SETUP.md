# Setup

## Prerequisites

- Docker (24+) -- the only hard requirement for the Docker-based workflow.
- For native (non-Docker) development: Python 3.12, Node.js 20.18+, and a
  local Postgres 16 + Redis 7 (or run just those two via Docker, see below).

## First-time setup

```bash
git clone <this-repo>
cd exchange

cp .env.example .env
# Edit .env: at minimum, set a real JWT_SECRET_KEY. Generate one with:
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Running everything (Docker, no Compose)

```bash
./scripts/docker-build.sh          # builds exchange/api-gateway and exchange/frontend
./scripts/docker-run.sh            # creates network/volume, starts postgres, redis,
                                    # runs migrations, starts gateway + frontend
```

Visit `http://localhost:3000` to register an account, or
`http://localhost:8000/docs` for interactive API docs (disabled in
production builds).

Tear down with `./scripts/docker-stop.sh` (or `--clean` to also delete the
Postgres volume -- this deletes all local data).

## Running services natively

See the root [README](../README.md#option-b----run-services-natively-faster-iteration)
for the exact commands. In short: start Postgres + Redis via Docker, then
run the gateway with `uvicorn --reload` and the frontend with `npm run dev`
for fast iteration without rebuilding images on every change.

## Running the test suite

The gateway's tests run against a **real** Postgres and Redis (not SQLite
mocks), because the schema uses Postgres-native types (UUID, ENUM) that
SQLite doesn't faithfully emulate, and because financial-system code
deserves tests against the real database engine it will run on in
production.

```bash
# Make sure exchange-postgres and exchange-redis are running (see above), then:
cd services/api-gateway
export TEST_DATABASE_URL=postgresql+asyncpg://exchange:exchange@localhost:5432/exchange_test
pytest --cov=app --cov-report=term-missing
```

CI provisions its own throwaway Postgres/Redis service containers per run
(`.github/workflows/ci.yml`) -- you don't need to replicate that locally
beyond having the two containers up.

## Common issues

**`alembic upgrade head` fails with "connection refused"**
Postgres isn't reachable yet -- check `docker ps`, and that `DATABASE_URL`
in your `.env` points at the right host (`localhost` when running natively,
the container name `exchange-postgres` when running inside `exchange-net`).

**Frontend shows a network error on login/register**
Check `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local` -- it must point
at the gateway's `/api/v1` prefix, and the gateway's `CORS_ORIGINS` env var
must include the frontend's origin.

**`docker-run.sh` hangs at "Waiting for Postgres and Redis to report healthy"**
Run `docker logs exchange-postgres` / `docker logs exchange-redis` to see
why the container itself isn't becoming healthy -- usually a stale volume
from a previous run with different credentials. `./scripts/docker-stop.sh
--clean` and try again.

**Registration returns 429 during local testing**
You've hit the rate limiter (`RATE_LIMIT_REGISTER_ATTEMPTS` per
`RATE_LIMIT_REGISTER_WINDOW_SECONDS`, defaults 3 per hour per IP). Either
wait, or lower the limits in your local `.env` -- don't disable rate
limiting in staging/production config.

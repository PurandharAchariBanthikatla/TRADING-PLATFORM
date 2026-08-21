# Deployment

## Current status

The CD pipeline (`.github/workflows/cd.yml`) builds and pushes immutable,
commit-SHA-tagged images for every service on every successful merge to
`main`, then walks through staging deploy → smoke test → **required manual
approval** → production deploy → smoke test. The deploy steps themselves
are placeholders until real staging/production hosts and a registry are
provisioned -- see the comments at the top of that workflow file for exactly
what to fill in.

## Image tagging

Every image is tagged twice: with the git commit SHA (immutable, for
rollback) and with `latest` (convenience, not used for actual deploys).
Always deploy by SHA, never by `latest`, so a rollback is just "redeploy
the previous SHA."

## Rollback procedure (once real hosts exist)

1. Identify the last known-good commit SHA (the previous successful CD run).
2. On the target host: `docker pull <registry>/<image>:<previous-sha>` for
   each service.
3. Re-run `scripts/docker-run.sh <previous-sha>` (the scripts accept a tag
   argument) -- this stops nothing that's still healthy; it replaces the
   gateway and frontend containers in place.
4. Run the smoke-test checks from `cd.yml` manually against the rolled-back
   version before considering the rollback complete.
5. If the rollback involved a database migration, see "Migration safety"
   below -- do not skip this step.

## Migration safety

Alembic migrations in this repo should be written to be backward-compatible
for at least one deploy cycle where practical (additive changes first,
destructive changes -- drops, renames -- in a follow-up migration once the
old code path is confirmed gone from production). This keeps rollback safe:
rolling back the application code should never require rolling back the
schema in the same step.

`./scripts/docker-run.sh` runs `alembic upgrade head` as a one-off container
before starting the gateway, so a bad migration fails loudly before any
traffic hits the new code.

## Zero/minimal-downtime deploys

Not yet implemented -- `docker-run.sh` currently does a stop-and-replace on
the gateway/frontend containers, which has a brief gap. The planned
approach once a real host is provisioned: start the new container, wait for
its `/health/ready` to pass, flip a reverse-proxy/load-balancer target to
it, then stop the old container. This is a concrete near-term follow-up,
not a design decision to skip minimal-downtime deploys permanently.

## Backup / disaster recovery

Not yet implemented for this phase (no financial data exists yet to back
up). Before the ledger/wallet services land, this doc will be expanded with:
Postgres backup schedule and retention, point-in-time recovery procedure,
a documented recovery-time/recovery-point objective, and a tested (not just
written) restore drill.

## Observability during deploys

Not yet implemented. Planned: Prometheus scrape targets on `/metrics` per
service, Grafana dashboards keyed on the four golden signals (latency,
traffic, errors, saturation), and deploy-correlated log markers so a
regression can be traced back to the exact SHA that introduced it.

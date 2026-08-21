# Architecture

## Current state (phase 3 complete: ledger + wallet + market data; phases 4-5 not started)

```
                    ┌─────────────┐
   browser  ──────▶ │  frontend    │  Next.js 14, App Router
                    │  (port 3000) │  auth pages + dashboard shell
                    └──────┬───────┘
                           │ REST (JSON, HTTPS in prod)
                           ▼
                    ┌──────────────┐        ┌────────────┐
                    │ api-gateway  │──────▶ │  Postgres  │  users, refresh_tokens
                    │ (FastAPI,    │        └────────────┘
                    │  port 8000)  │        ┌────────────┐
                    │              │──────▶ │   Redis    │  rate-limit counters (db 0)
                    └──────────────┘        └────────────┘

                    ┌──────────────┐        ┌────────────┐
                    │ wallet-      │──────▶ │  Postgres  │  wallets, wallet_deposits,
                    │ service      │        │  (same DB, │  wallet_withdrawal_requests,
                    │ (FastAPI,    │        │  separate  │  wallet_internal_transfers
                    │  internal    │        │  tables)   │
                    │  only)       │        └────────────┘
                    └──────┬───────┘
                           │ REST, X-Internal-Service-Key auth
                           ▼
                    ┌──────────────┐        ┌────────────┐
                    │ ledger-      │──────▶ │  Postgres  │  ledger_accounts,
                    │ service      │        │  (same DB, │  ledger_transactions,
                    │ (FastAPI,    │        │  separate  │  ledger_entries
                    │  internal    │        │  tables)   │
                    │  only)       │        └────────────┘
                    └──────────────┘

                    ┌──────────────┐        ┌────────────┐
                    │ market-data- │──────▶ │  Postgres  │  assets, markets,
                    │ service      │        │  (same DB, │  market_trades,
                    │ (FastAPI +   │        │  separate  │  market_candles,
                    │  3 background│        │  tables)   │  market_orderbook_snapshots
                    │  loops,      │        └────────────┘
                    │  internal    │        ┌────────────┐
                    │  only)       │──────▶ │   Redis    │  event streams (db 1) +
                    └──────────────┘        │  Streams   │  ticker cache
                                             └────────────┘
```

api-gateway, ledger-service, wallet-service, market-data-service, and
frontend each run in their own container on a shared Docker network
(`exchange-net`, created by `scripts/docker-run.sh`). Only the gateway and
frontend publish ports to the host; Postgres, Redis, and every internal
service are reachable only from other containers on that network,
matching how they'll be deployed in staging/production. All backend
services currently share one Postgres *instance* but each owns its tables
outright (no cross-service foreign keys) -- none of the phase 2/3 services
are reachable from the frontend yet, since api-gateway doesn't proxy to
them (tracked for phase 5, when the trading UI needs it).

wallet-service is a pure orchestration layer: it never computes or writes
a balance itself, it only calls ledger-service's `POST /ledger/transactions`
(via `app/clients/ledger_client.py`) and keeps its own tables for
idempotency bookkeeping, the withdrawal approval workflow's state machine,
and fast history queries. See "Data model (phase 2: wallet-service)" below.

market-data-service is self-contained: unlike wallet-service, it doesn't
call any other backend service. It runs three background asyncio loops
in-process (producer, candle consumer, DLQ maintenance -- see "Data model
(phase 3: market-data-service)" below) publishing to and consuming from
its own Redis Streams, with Postgres as the durable source of truth for
everything the streams distribute.

All three internal services trust access tokens minted by api-gateway
(same `JWT_SECRET_KEY`/`JWT_ALGORITHM`, verified only, never issued)
rather than keeping their own copy of user identity -- see
`app/api/deps.py` in each service. Service-to-service calls (wallet-service
-> ledger-service) use a separate shared secret, `X-Internal-Service-Key`
(same value in every backend service's env) -- see "Service-to-service
auth" below. Most of market-data-service's read endpoints (ticker,
candles, trades, order book) are deliberately public/unauthenticated --
market data isn't user-specific -- while asset/market configuration
endpoints are admin/service-gated like the others.

## Target end-state architecture

The gateway is deliberately thin: authentication, request validation, and
routing. As later phases land, it starts proxying into dedicated internal
services rather than growing a monolith:

```
frontend ──▶ api-gateway (FastAPI, REST + WebSocket) ──▶ trading-engine
                                                      ──▶ matching-engine
                                                      ──▶ market-data-service
                                                      ──▶ wallet-service
                                                      ──▶ ledger-service (immutable, double-entry)
                                                      ──▶ risk-engine
                                                      ──▶ settlement-service
                                                      ──▶ notification-service
                                                      ──▶ reporting-service
```

Kafka/Redpanda sits between the matching engine and the services that react
to trade/order events (ledger, notifications, reporting, market-data) once
that phase starts -- not needed yet for the auth-only slice.

## Key decisions and why

- **Postgres is the source of truth** for everything transactional. Redis is
  cache/session/rate-limit state only -- nothing that would be catastrophic
  to lose is ever Redis-only.
- **Access tokens are short-lived (15 min) and stateless.** Refresh tokens
  are long-lived, rotated on every use, and their `jti` is persisted so a
  specific session can be revoked. See the docstring on
  `app.api.deps.get_current_user` for the exact revocation model and its
  known limitation (a stolen access token remains valid for up to 15
  minutes after logout) -- fixing that is a deliberate later phase (session
  management screen + `tokens_valid_after` check), not an oversight.
- **No Docker Compose**, per project constraint. `scripts/docker-run.sh`
  reproduces what Compose would normally do (network, volumes, container
  dependency ordering, health-gated startup) with plain `docker` commands
  so the same commands work identically in CI, on a bare Docker host in
  staging, and locally.
- **Every table gets a UUID primary key and audit timestamps**
  (`app/db/base.py`) as a repo-wide convention, so nothing added later is
  untraceable by default.
- **Structured JSON logs + request-ID correlation** from day one
  (`app/core/logging.py`, `app/middleware/request_id.py`) -- retrofitting
  this after several services exist is much more painful than starting with
  it.

## Data model (phase 1: api-gateway)

```
users
  id (uuid, pk)
  email (unique)
  hashed_password
  display_name
  role (enum: user | admin)
  is_active, is_email_verified
  mfa_enabled, mfa_secret_encrypted (nullable -- MFA enrollment is a later phase)
  created_at, updated_at

refresh_tokens
  id (uuid, pk)
  user_id (fk -> users.id, cascade delete)
  jti (unique)              -- the token itself is never stored, only its id
  expires_at
  revoked (bool)
  user_agent, ip_address    -- basis for a future "active sessions" screen
  created_at, updated_at
```

## Data model (phase 2: ledger-service)

```
ledger_accounts
  id (uuid, pk)
  owner_type (enum: user | system)
  owner_id (uuid, nullable -- null for system accounts)
  asset (e.g. "BTC", "USDT")
  account_type (enum: user_available | user_locked | user_pending |
                       system_reserve | system_fee_revenue | system_suspense)
  balance (numeric(38,18) -- cached; source of truth is the sum of
           ledger_entries for this account, see reconcile_account())
  created_at, updated_at
  -- unique per (owner_id, asset, account_type) for user accounts,
  -- unique per (asset, account_type) for system accounts (partial indexes)

ledger_transactions
  id (uuid, pk)
  reference (unique)         -- caller-supplied idempotency key
  source_type (enum: deposit | withdrawal | internal_transfer | trade |
                      fee | adjustment | settlement)
  status (enum: posted | reversed)
  description
  transaction_metadata (jsonb -- order_id, deposit tx hash, etc.)
  posted_at
  created_at, updated_at

ledger_entries
  id (uuid, pk)
  transaction_id (fk -> ledger_transactions.id)
  account_id (fk -> ledger_accounts.id)
  direction (enum: debit | credit)
  asset
  amount (numeric(38,18), > 0 -- direction encodes sign, not the amount)
  balance_after (numeric(38,18) -- denormalized checkpoint for statements
                 and reconciliation, see model docstring)
  created_at, updated_at
```

**Double-entry invariant** (enforced in `app/core/ledger_engine.py`,
`post_transaction()` -- the only code path allowed to write a balance):
every transaction has ≥2 entries, and for each asset present in the
transaction, `sum(credit amounts) == sum(debit amounts)`. A trade moving
BTC one way and USDT the other posts as one transaction with two
independently-balanced per-asset legs, cleared through
`system_suspense` accounts -- see `test_multi_asset_transaction_must_balance_per_asset`
in `services/ledger-service/tests/test_ledger_engine.py`.

**Concurrency:** accounts touched by a transaction are locked with
`SELECT ... FOR UPDATE` in a deterministic (id-sorted) order before any
balance is read, so overlapping concurrent transactions serialize instead
of racing or deadlocking -- exercised by
`test_concurrent_deposits_to_same_account_serialize_correctly`.

**Reconciliation:** `reconcile_account()` recomputes a balance from full
entry history and compares it to the cached column; any divergence is a
P0 bug (something bypassed `post_transaction()`), not an "out of date"
state. `GET /ledger/accounts/{id}/reconcile` (admin-only) exposes this on
demand; wiring it into a scheduled job is phase 8 (observability).

**Known gap, tracked, not silently skipped:** `POST /ledger/transactions`
and system-account provisioning are gated to `role in (admin, service)`.
wallet-service is the first real `service` caller; matching/risk/
settlement services will be others in later phases. There is currently no
per-service scoping on the shared key -- any holder of it gets full
`service` trust. A proper service-identity mechanism (mTLS client certs or
short-lived service JWTs from a dedicated authority) is real follow-up
work before this could ever front real funds, not something to gold-plate
during phase 2.

## Service-to-service auth

wallet-service calls ledger-service using a shared secret,
`X-Internal-Service-Key` (identical value in both services' env,
`INTERNAL_SERVICE_KEY`), plus `X-Internal-Service-Name` identifying the
caller for logging. See `ledger-service/app/api/deps.py` (`get_caller`,
`require_admin_or_service`) for the verification side and
`wallet-service/app/clients/ledger_client.py` for the calling side. This
is separate from, and does not replace, the user-facing JWT auth described
above -- a request either carries a valid user/admin JWT or a valid
internal-service key, never both required together.

## Data model (phase 2: wallet-service)

```
wallets
  id (uuid, pk)
  user_id (uuid)
  asset
  ledger_available_account_id, ledger_locked_account_id,
  ledger_pending_account_id (uuid -- ids of the three ledger-service
    accounts backing this wallet; wallet-service holds no balance itself)
  created_at, updated_at
  -- unique per (user_id, asset)

wallet_deposits
  id (uuid, pk)
  wallet_id (fk -> wallets.id)
  reference (unique)          -- idempotency key
  asset, amount
  status (enum: pending | confirmed | failed -- paper funds settle
          synchronously, so this reaches `confirmed` immediately or
          `failed`; `pending` exists for a future real-deposit flow)
  ledger_transaction_reference
  deposit_metadata (jsonb)
  created_at, updated_at

wallet_withdrawal_requests
  id (uuid, pk)
  wallet_id (fk -> wallets.id)
  reference (unique)
  asset, amount, destination  -- paper/sandbox destination label, not a
                                  real chain address
  status (enum: pending_approval | approved | rejected | completed | failed)
  lock_ledger_reference       -- the available->locked ledger transaction
  settlement_ledger_reference -- the locked->reserve (approved) or
                                  locked->available (rejected) transaction
  reviewed_by_user_id (string, not a UUID fk -- may be an admin's user id
                        as text, or a service identity like
                        "service:risk-engine" in a later phase)
  reviewed_at, rejection_reason
  withdrawal_metadata (jsonb)
  created_at, updated_at

wallet_internal_transfers
  id (uuid, pk)
  from_wallet_id, to_wallet_id (fk -> wallets.id)
  reference (unique)
  asset, amount
  status (enum: completed | failed)
  ledger_transaction_reference
  created_at, updated_at
```

**Withdrawal lifecycle** (`app/core/wallet_engine.py`): `request_withdrawal`
locks funds immediately -- a same-asset `internal_transfer` ledger
transaction moving `USER_AVAILABLE` -> `USER_LOCKED` -- so the funds can't
be spent elsewhere while the request is pending, before any admin action.
`approve_withdrawal` posts `USER_LOCKED` -> `SYSTEM_RESERVE` (source_type
`withdrawal`) and marks `completed`. `reject_withdrawal` posts
`USER_LOCKED` -> `USER_AVAILABLE` (source_type `internal_transfer`) and
marks `rejected`. Both are only valid from `pending_approval`; re-approving
or re-rejecting an already-resolved request raises
`InvalidWithdrawalStateError` rather than silently re-posting a second
release -- see `test_cannot_approve_same_withdrawal_twice` and
`test_cannot_reject_an_already_rejected_withdrawal`.

**Withdrawal limits** are flat (`MAX_WITHDRAWAL_PER_TRANSACTION`,
`MAX_WITHDRAWAL_PER_DAY`), not asset-aware or KYC-tiered yet -- per-asset
precision arrives with phase 3 (market/asset configuration), tiered limits
with phase 7 (admin).

**Idempotency**, identically to ledger-service: every mutating wallet
operation takes a caller-supplied `reference`, checks its own table for
an existing row first, and if a concurrent duplicate slips through, catches
the resulting `IntegrityError` on insert and returns the winner's row
instead of erroring -- see `test_deposit_is_idempotent_by_reference` and
`test_wallet_creation_is_idempotent_under_concurrency`.

## Data model (phase 3: market-data-service)

```
assets
  id (uuid, pk)
  symbol (unique), name, decimals, is_active

markets
  id (uuid, pk)
  symbol (unique, e.g. "BTC-USDT"), base_asset, quote_asset
  status (enum: trading | halted | delisted)
  price_precision, quantity_precision (int -- display only)
  tick_size, lot_size (numeric -- a valid price/quantity must be an exact
                        multiple; see app/core/precision.py)
  min_quantity, max_quantity, min_notional
  maker_fee_bps, taker_fee_bps
  is_active

market_trades
  id (uuid, pk)
  market_id (fk), sequence (unique per market, monotonic)
  price, quantity, side (buy|sell)
  source (enum: simulated | matching_engine -- phase 3 writes only
          `simulated`; phase 4 will write `matching_engine` rows into
          this exact same table)
  occurred_at

market_candles
  id (uuid, pk)
  market_id (fk), interval (1m|5m|15m|1h|4h|1d), open_time
  open, high, low, close, volume, quote_volume, trade_count
  last_trade_sequence  -- dedup checkpoint, see candle_aggregator.py
  -- unique per (market_id, interval, open_time)

market_orderbook_snapshots
  id (uuid, pk)
  market_id (fk), sequence (unique per market, monotonic)
  bids, asks (jsonb: [[price, quantity], ...], best-first)
  snapshot_time
```

**Why Redis Streams instead of Kafka/Redpanda:** the target architecture
calls for Kafka/Redpanda for market-data event distribution. This
environment has no broker infrastructure available, and standing one up
is real ops work independent of application code -- not something to
silently paper over. `app/core/event_bus.py` uses Redis Streams as the
concrete backing implementation instead, chosen because it actually
provides the properties this phase requires and tests (ordered per-stream
log, consumer groups, per-consumer delivery tracking, explicit ack,
reclaim-on-timeout for retry/DLQ via `XPENDING`/`XCLAIM`) rather than a
pub/sub stand-in that fakes them. The module's public interface
(`publish`, `consume_group`, `ack`, `claim_stale_and_deadletter`) is
broker-agnostic on purpose: swapping to a real Kafka/Redpanda client later
is a rewrite of that one module, not a change to any caller.

**Paper-data simulator, not mocked frontend data:** phase 3 has no
matching engine yet (phase 4), so `app/core/simulator.py` and
`app/core/orderbook_simulator.py` generate deterministic (seeded by
`(SIMULATOR_SEED, market.symbol)`), on-tick/on-lot synthetic trades and
order-book snapshots through the *real* backend pipeline -- persisted to
Postgres, published to the event bus -- specifically so this is not
frontend-mocked data. `Trade.source` and the producer/consumer split are
designed so phase 4 is a producer swap (real matching engine writes
`source=matching_engine` trades onto the same streams), not a rewrite of
anything downstream (candle aggregation, ticker, the API, or the future
WebSocket gateway).

**Idempotent consumption under at-least-once delivery:**
`app/core/candle_aggregator.py`'s `handle_trade_event()` is safe to call
twice with the identical event -- it checks each candle's
`last_trade_sequence` before folding a trade in and no-ops on redelivery,
since trade sequences are monotonic per market. This matters because
Redis Streams consumer groups (like Kafka/Redpanda) only guarantee
at-least-once delivery: a consumer that crashes after processing but
before `XACK` will have its message reclaimed and redelivered. Verified
directly (`test_redelivered_event_is_a_no_op`,
`test_out_of_order_redelivery_of_earlier_sequence_is_also_a_no_op`) and
implicitly by the live smoke test's candle `trade_count` exactly matching
the ticker's `trade_count_24h` with zero drift.

**Dead-lettering:** an event whose `event_version` a consumer doesn't
recognize is deliberately left un-acked rather than skipped or guessed at
(see `UnsupportedEventVersionError` in `candle_aggregator.py`); the
`dlq_maintenance_loop` background task then moves it to `{stream}.dlq`
after `EVENT_STREAM_MAX_DELIVERY_ATTEMPTS` failed redeliveries, so one bad
event can't loop forever or silently vanish.

## Two real bugs phase 2 caught (and why unit tests alone didn't)

Both were only found because wallet-service's test suite runs against a
**live, migration-provisioned** ledger-service instance over real HTTP
(see `services/wallet-service/tests/conftest.py` and the
`wallet-service-checks` CI job) instead of only exercising ledger-service
in-process. Worth recording so the pattern isn't lost:

1. **Enum value/name mismatch.** SQLAlchemy's `Enum(python_enum_class)`
   binds using the member's `.name` (e.g. `"USER"`) by default, not
   `.value` (`"user"`), unless `values_callable` is passed. Every Alembic
   migration in both services defines the native Postgres enum labels
   using lowercase `.value` strings (to match the JSON API contract). That
   mismatch was invisible in tests using `Base.metadata.create_all()`
   (self-consistent with SQLAlchemy's own default) but broke every enum
   column the moment a real `alembic upgrade head`-provisioned database
   was used -- exactly what `scripts/docker-run.sh` does. Fixed by adding
   `values_callable=lambda obj: [e.value for e in obj]` to every `Enum(...)`
   column in both services (8 sites total).
2. **Unhandled get-or-create race.** `ledger-service`'s
   `POST /ledger/accounts` did a `SELECT` then an `INSERT` with no race
   handling; two simultaneous requests for the same (owner, asset,
   account_type) both pass the `SELECT`, and the loser's `INSERT` throws
   an unhandled `IntegrityError` (500) on the partial unique index instead
   of returning the winner's row. wallet-service's own
   `get_or_create_wallet` already had the correct pattern (catch
   `IntegrityError`, rollback, re-fetch); ledger-service's route didn't.
   Fixed to match, and covered by
   `test_concurrent_get_or_create_account_does_not_500` in ledger-service
   and confirmed with three genuinely concurrent `curl` requests against a
   live instance, which now all return the identical account id.

## Real bugs phase 3 caught

1. **Native enum DDL double-creation.** Every migration that defines a
   Postgres native `ENUM` type explicitly (to control creation order) and
   then reuses that same `ENUM` object as a column type in `create_table`
   must pass `create_type=False` to the `ENUM(...)` constructor --
   otherwise SQLAlchemy's DDL compiler tries to `CREATE TYPE` a second
   time as part of the table DDL and the migration fails with "type
   already exists". ledger-service's migration already had this right;
   market-data-service's initial migration didn't (copy/paste gap, not a
   new discovery) and failed identically until fixed the same way.
2. **`Mapped[float]` vs `Mapped[Decimal]` on Numeric columns.** Columns
   that are ever reassigned after object construction (not just passed to
   the constructor) need `Mapped[Decimal]`, not `Mapped[float]`, or mypy
   correctly flags the assignment as a type error -- `Mapped[float]`
   happens to type-check fine for fields that are only ever set at
   construction time (e.g. `wallet-service`'s `Deposit.amount`), which is
   why this wasn't caught earlier; `market-data-service`'s
   `Candle.high/low/close/volume/quote_volume` are mutated in place by
   `candle_aggregator.py` and immediately surfaced it.
3. **`Decimal.quantize()` rounds to a matching *exponent*, not to
   multiples of its argument's *value*.** `app/core/simulator.py`
   initially used `(min_notional / price).quantize(lot_size, ...)` to
   round a quantity up to satisfy `min_notional`, expecting it to round to
   the nearest multiple of `lot_size`. It instead rounded to match
   `lot_size`'s stored decimal-place count (18, from the `NUMERIC(38,18)`
   column), producing quantities like `0.009995002498750625` that aren't
   lot-size multiples at all. Fixed with explicit integer ceiling
   division (`(x / lot_size).to_integral_value(rounding=ROUND_CEILING) *
   lot_size`) instead of `quantize()`. Caught by
   `test_generated_trades_respect_market_precision`, which round-trips
   every simulator-generated trade back through the same
   `validate_order_shape()` the matching engine will use in phase 4.

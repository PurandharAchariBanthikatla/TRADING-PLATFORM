"""initial: assets, markets, market_trades, market_candles, market_orderbook_snapshots

Revision ID: 0001
Revises:
Create Date: 2026-08-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MARKET_STATUSES = ("trading", "halted", "delisted")
TRADE_SIDES = ("buy", "sell")
TRADE_SOURCES = ("simulated", "matching_engine")
CANDLE_INTERVALS = ("1m", "5m", "15m", "1h", "4h", "1d")


def upgrade() -> None:
    bind = op.get_bind()

    market_status = postgresql.ENUM(*MARKET_STATUSES, name="market_status", create_type=False)
    trade_side = postgresql.ENUM(*TRADE_SIDES, name="market_trade_side", create_type=False)
    trade_source = postgresql.ENUM(*TRADE_SOURCES, name="market_trade_source", create_type=False)
    candle_interval = postgresql.ENUM(*CANDLE_INTERVALS, name="market_candle_interval", create_type=False)

    # create_type=False on every one of these: we create the Postgres enum
    # type explicitly, once, below. Without create_type=False, SQLAlchemy's
    # DDL compiler additionally tries to (re)create the enum type as part
    # of each create_table() call that references it as a column type,
    # which fails with "type already exists" the second time around.
    for enum_type in (market_status, trade_side, trade_source, candle_interval):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("decimals", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_unique_constraint("uq_assets_symbol", "assets", ["symbol"])
    op.create_index("ix_assets_symbol", "assets", ["symbol"])

    op.create_table(
        "markets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("base_asset", sa.String(length=20), nullable=False),
        sa.Column("quote_asset", sa.String(length=20), nullable=False),
        sa.Column("status", market_status, nullable=False, server_default="trading"),
        sa.Column("price_precision", sa.Integer(), nullable=False),
        sa.Column("quantity_precision", sa.Integer(), nullable=False),
        sa.Column("tick_size", sa.Numeric(38, 18), nullable=False),
        sa.Column("lot_size", sa.Numeric(38, 18), nullable=False),
        sa.Column("min_quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("max_quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("min_notional", sa.Numeric(38, 18), nullable=False, server_default="0"),
        sa.Column("maker_fee_bps", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("taker_fee_bps", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("tick_size > 0", name="ck_markets_tick_size_positive"),
        sa.CheckConstraint("lot_size > 0", name="ck_markets_lot_size_positive"),
        sa.CheckConstraint("min_quantity > 0", name="ck_markets_min_quantity_positive"),
        sa.CheckConstraint("max_quantity > min_quantity", name="ck_markets_max_gt_min_quantity"),
    )
    op.create_unique_constraint("uq_markets_symbol", "markets", ["symbol"])
    op.create_index("ix_markets_symbol", "markets", ["symbol"])

    op.create_table(
        "market_trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "market_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("markets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(38, 18), nullable=False),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("side", trade_side, nullable=False),
        sa.Column("source", trade_source, nullable=False, server_default="simulated"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ux_market_trades_market_sequence", "market_trades", ["market_id", "sequence"], unique=True)
    op.create_index("ix_market_trades_market_occurred_at", "market_trades", ["market_id", "occurred_at"])

    op.create_table(
        "market_candles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "market_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("markets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("interval", candle_interval, nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(38, 18), nullable=False),
        sa.Column("high", sa.Numeric(38, 18), nullable=False),
        sa.Column("low", sa.Numeric(38, 18), nullable=False),
        sa.Column("close", sa.Numeric(38, 18), nullable=False),
        sa.Column("volume", sa.Numeric(38, 18), nullable=False, server_default="0"),
        sa.Column("quote_volume", sa.Numeric(38, 18), nullable=False, server_default="0"),
        sa.Column("trade_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_trade_sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ux_market_candles_market_interval_open_time",
        "market_candles",
        ["market_id", "interval", "open_time"],
        unique=True,
    )

    op.create_table(
        "market_orderbook_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "market_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("markets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("bids", postgresql.JSONB(), nullable=False),
        sa.Column("asks", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ux_orderbook_snapshots_market_sequence",
        "market_orderbook_snapshots",
        ["market_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("market_orderbook_snapshots")
    op.drop_index("ux_market_candles_market_interval_open_time", table_name="market_candles")
    op.drop_table("market_candles")
    op.drop_index("ix_market_trades_market_occurred_at", table_name="market_trades")
    op.drop_index("ux_market_trades_market_sequence", table_name="market_trades")
    op.drop_table("market_trades")
    op.drop_index("ix_markets_symbol", table_name="markets")
    op.drop_table("markets")
    op.drop_index("ix_assets_symbol", table_name="assets")
    op.drop_table("assets")

    bind = op.get_bind()
    for enum_name in ("market_candle_interval", "market_trade_source", "market_trade_side", "market_status"):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)

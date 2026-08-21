"""initial: ledger_accounts, ledger_transactions, ledger_entries

Revision ID: 0001
Revises:
Create Date: 2026-08-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWNER_TYPES = ("user", "system")
ACCOUNT_TYPES = (
    "user_available",
    "user_locked",
    "user_pending",
    "system_reserve",
    "system_fee_revenue",
    "system_suspense",
)
SOURCE_TYPES = (
    "deposit",
    "withdrawal",
    "internal_transfer",
    "trade",
    "fee",
    "adjustment",
    "settlement",
)
TXN_STATUSES = ("posted", "reversed")
ENTRY_DIRECTIONS = ("debit", "credit")


def upgrade() -> None:
    bind = op.get_bind()

    # create_type=False on every one of these: we create the Postgres enum
    # types explicitly (once, below, with checkfirst) and then only ever
    # reference these same Python objects when declaring columns. Without
    # create_type=False, SQLAlchemy's DDL compiler additionally tries to
    # CREATE TYPE again the first time each enum is used in a column
    # definition (it does not know the type was already created out of
    # band), which fails with "type already exists" on a truly fresh
    # database -- this bit us the first time this migration was written.
    ledger_owner_type = postgresql.ENUM(*OWNER_TYPES, name="ledger_owner_type", create_type=False)
    ledger_account_type = postgresql.ENUM(*ACCOUNT_TYPES, name="ledger_account_type", create_type=False)
    ledger_transaction_source_type = postgresql.ENUM(
        *SOURCE_TYPES, name="ledger_transaction_source_type", create_type=False
    )
    ledger_transaction_status = postgresql.ENUM(
        *TXN_STATUSES, name="ledger_transaction_status", create_type=False
    )
    ledger_entry_direction = postgresql.ENUM(*ENTRY_DIRECTIONS, name="ledger_entry_direction", create_type=False)

    for enum_type in (
        ledger_owner_type,
        ledger_account_type,
        ledger_transaction_source_type,
        ledger_transaction_status,
        ledger_entry_direction,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "ledger_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("owner_type", ledger_owner_type, nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("asset", sa.String(length=20), nullable=False),
        sa.Column("account_type", ledger_account_type, nullable=False),
        sa.Column("balance", sa.Numeric(38, 18), nullable=False, server_default="0"),
    )
    op.create_index(
        "ux_ledger_accounts_user",
        "ledger_accounts",
        ["owner_id", "asset", "account_type"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NOT NULL"),
    )
    op.create_index(
        "ux_ledger_accounts_system",
        "ledger_accounts",
        ["asset", "account_type"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NULL"),
    )
    op.create_index("ix_ledger_accounts_owner_id", "ledger_accounts", ["owner_id"])

    op.create_table(
        "ledger_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=False),
        sa.Column("source_type", ledger_transaction_source_type, nullable=False),
        sa.Column("status", ledger_transaction_status, nullable=False, server_default="posted"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("transaction_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversal_of_id", sa.String(length=36), nullable=True),
    )
    op.create_unique_constraint("uq_ledger_transactions_reference", "ledger_transactions", ["reference"])
    op.create_index("ix_ledger_transactions_reference", "ledger_transactions", ["reference"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("direction", ledger_entry_direction, nullable=False),
        sa.Column("asset", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("balance_after", sa.Numeric(38, 18), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_ledger_entries_amount_positive"),
    )
    op.create_index("ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"])
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_ledger_entries_account_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_transaction_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")

    op.drop_index("ix_ledger_transactions_reference", table_name="ledger_transactions")
    op.drop_table("ledger_transactions")

    op.drop_index("ix_ledger_accounts_owner_id", table_name="ledger_accounts")
    op.drop_index("ux_ledger_accounts_system", table_name="ledger_accounts")
    op.drop_index("ux_ledger_accounts_user", table_name="ledger_accounts")
    op.drop_table("ledger_accounts")

    bind = op.get_bind()
    for enum_name in (
        "ledger_entry_direction",
        "ledger_transaction_status",
        "ledger_transaction_source_type",
        "ledger_account_type",
        "ledger_owner_type",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)

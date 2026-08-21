"""initial: wallets, wallet_deposits, wallet_withdrawal_requests, wallet_internal_transfers

Revision ID: 0001
Revises:
Create Date: 2026-08-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEPOSIT_STATUSES = ("pending", "confirmed", "failed")
WITHDRAWAL_STATUSES = ("pending_approval", "approved", "rejected", "completed", "failed")
TRANSFER_STATUSES = ("completed", "failed")


def upgrade() -> None:
    bind = op.get_bind()

    wallet_deposit_status = postgresql.ENUM(*DEPOSIT_STATUSES, name="wallet_deposit_status", create_type=False)
    wallet_withdrawal_status = postgresql.ENUM(
        *WITHDRAWAL_STATUSES, name="wallet_withdrawal_status", create_type=False
    )
    wallet_transfer_status = postgresql.ENUM(*TRANSFER_STATUSES, name="wallet_transfer_status", create_type=False)

    for enum_type in (wallet_deposit_status, wallet_withdrawal_status, wallet_transfer_status):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "wallets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset", sa.String(length=20), nullable=False),
        sa.Column("ledger_available_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ledger_locked_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ledger_pending_account_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_index("ux_wallets_user_asset", "wallets", ["user_id", "asset"], unique=True)

    op.create_table(
        "wallet_deposits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "wallet_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("reference", sa.String(length=255), nullable=False),
        sa.Column("asset", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("status", wallet_deposit_status, nullable=False, server_default="pending"),
        sa.Column("ledger_transaction_reference", sa.String(length=255), nullable=True),
        sa.Column("deposit_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.CheckConstraint("amount > 0", name="ck_wallet_deposits_amount_positive"),
    )
    op.create_unique_constraint("uq_wallet_deposits_reference", "wallet_deposits", ["reference"])
    op.create_index("ix_wallet_deposits_reference", "wallet_deposits", ["reference"])
    op.create_index("ix_wallet_deposits_wallet_id", "wallet_deposits", ["wallet_id"])

    op.create_table(
        "wallet_withdrawal_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "wallet_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("reference", sa.String(length=255), nullable=False),
        sa.Column("asset", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("destination", sa.String(length=500), nullable=False),
        sa.Column("status", wallet_withdrawal_status, nullable=False, server_default="pending_approval"),
        sa.Column("lock_ledger_reference", sa.String(length=255), nullable=False),
        sa.Column("settlement_ledger_reference", sa.String(length=255), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("withdrawal_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.CheckConstraint("amount > 0", name="ck_wallet_withdrawals_amount_positive"),
    )
    op.create_unique_constraint("uq_wallet_withdrawals_reference", "wallet_withdrawal_requests", ["reference"])
    op.create_index("ix_wallet_withdrawals_reference", "wallet_withdrawal_requests", ["reference"])
    op.create_index("ix_wallet_withdrawals_wallet_id", "wallet_withdrawal_requests", ["wallet_id"])
    op.create_index(
        "ix_wallet_withdrawals_wallet_id_created_at", "wallet_withdrawal_requests", ["wallet_id", "created_at"]
    )

    op.create_table(
        "wallet_internal_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "from_wallet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "to_wallet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wallets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(length=255), nullable=False),
        sa.Column("asset", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("status", wallet_transfer_status, nullable=False, server_default="completed"),
        sa.Column("ledger_transaction_reference", sa.String(length=255), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_wallet_transfers_amount_positive"),
    )
    op.create_unique_constraint("uq_wallet_transfers_reference", "wallet_internal_transfers", ["reference"])
    op.create_index("ix_wallet_transfers_reference", "wallet_internal_transfers", ["reference"])
    op.create_index("ix_wallet_transfers_from_wallet_id", "wallet_internal_transfers", ["from_wallet_id"])
    op.create_index("ix_wallet_transfers_to_wallet_id", "wallet_internal_transfers", ["to_wallet_id"])


def downgrade() -> None:
    op.drop_index("ix_wallet_transfers_to_wallet_id", table_name="wallet_internal_transfers")
    op.drop_index("ix_wallet_transfers_from_wallet_id", table_name="wallet_internal_transfers")
    op.drop_index("ix_wallet_transfers_reference", table_name="wallet_internal_transfers")
    op.drop_table("wallet_internal_transfers")

    op.drop_index("ix_wallet_withdrawals_wallet_id_created_at", table_name="wallet_withdrawal_requests")
    op.drop_index("ix_wallet_withdrawals_wallet_id", table_name="wallet_withdrawal_requests")
    op.drop_index("ix_wallet_withdrawals_reference", table_name="wallet_withdrawal_requests")
    op.drop_table("wallet_withdrawal_requests")

    op.drop_index("ix_wallet_deposits_wallet_id", table_name="wallet_deposits")
    op.drop_index("ix_wallet_deposits_reference", table_name="wallet_deposits")
    op.drop_table("wallet_deposits")

    op.drop_index("ux_wallets_user_asset", table_name="wallets")
    op.drop_table("wallets")

    bind = op.get_bind()
    for enum_name in ("wallet_transfer_status", "wallet_withdrawal_status", "wallet_deposit_status"):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)

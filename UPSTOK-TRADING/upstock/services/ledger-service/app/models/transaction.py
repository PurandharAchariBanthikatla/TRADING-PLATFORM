import enum
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TransactionSourceType(str, enum.Enum):
    """What kind of business event produced this transaction. Every new
    order/trade/fee/deposit/withdrawal/transfer/settlement flow that lands
    in later phases posts through app.core.ledger_engine.post_transaction
    with one of these -- there is deliberately no generic "other" bucket,
    because an untyped source_type is unauditable.
    """

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    INTERNAL_TRANSFER = "internal_transfer"
    TRADE = "trade"
    FEE = "fee"
    ADJUSTMENT = "adjustment"
    SETTLEMENT = "settlement"


class TransactionStatus(str, enum.Enum):
    POSTED = "posted"
    REVERSED = "reversed"


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"

    # Caller-supplied idempotency key. Re-posting the same reference returns
    # the original transaction instead of double-posting -- this is what
    # makes it safe for the wallet/matching/settlement services to retry a
    # timed-out call without risking a duplicate credit.
    reference: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    source_type: Mapped[TransactionSourceType] = mapped_column(
        SAEnum(
            TransactionSourceType,
            name="ledger_transaction_source_type",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(
            TransactionStatus,
            name="ledger_transaction_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=TransactionStatus.POSTED,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Free-form structured context (order_id, trade_id, deposit tx hash,
    # withdrawal request id, etc.) -- kept generic so this table doesn't
    # need a schema migration every time a new upstream event type appears.
    transaction_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    reversal_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper only
        return (
            f"<LedgerTransaction id={self.id} reference={self.reference!r} "
            f"source={self.source_type.value} status={self.status.value}>"
        )

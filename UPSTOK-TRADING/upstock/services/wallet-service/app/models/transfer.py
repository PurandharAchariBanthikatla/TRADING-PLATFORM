import enum
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TransferStatus(str, enum.Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class InternalTransfer(Base):
    """A same-asset transfer between two wallets' USER_AVAILABLE ledger
    accounts. Balances directly (single asset, one debit, one credit) --
    no clearing account needed, unlike a cross-asset trade.
    """

    __tablename__ = "wallet_internal_transfers"

    from_wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    to_wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reference: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    asset: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)
    status: Mapped[TransferStatus] = mapped_column(
        SAEnum(
            TransferStatus, name="wallet_transfer_status", values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
        default=TransferStatus.COMPLETED,
    )
    ledger_transaction_reference: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (CheckConstraint("amount > 0", name="ck_wallet_transfers_amount_positive"),)

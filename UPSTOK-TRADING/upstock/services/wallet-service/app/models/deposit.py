import enum
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DepositStatus(str, enum.Enum):
    # Paper funds settle synchronously -- there's no external chain
    # confirmation to wait on, so CONFIRMED is reached immediately (or
    # FAILED if the ledger call itself failed). PENDING exists for
    # forward-compatibility with a future real-deposit flow that needs to
    # wait for confirmations rather than because it's reachable today.
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class Deposit(Base):
    __tablename__ = "wallet_deposits"

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reference: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    asset: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)
    status: Mapped[DepositStatus] = mapped_column(
        SAEnum(
            DepositStatus, name="wallet_deposit_status", values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
        default=DepositStatus.PENDING,
    )
    ledger_transaction_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deposit_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (CheckConstraint("amount > 0", name="ck_wallet_deposits_amount_positive"),)

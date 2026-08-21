import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WithdrawalStatus(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"  # funds locked, awaiting admin review
    APPROVED = "approved"  # transient: approval in progress
    REJECTED = "rejected"  # funds released back to available
    COMPLETED = "completed"  # funds debited to system reserve, withdrawal settled
    FAILED = "failed"  # approval attempted but the settlement ledger call failed


class WithdrawalRequest(Base):
    __tablename__ = "wallet_withdrawal_requests"

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reference: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    asset: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False)
    destination: Mapped[str] = mapped_column(String(500), nullable=False)  # paper/sandbox destination label

    status: Mapped[WithdrawalStatus] = mapped_column(
        SAEnum(
            WithdrawalStatus,
            name="wallet_withdrawal_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=WithdrawalStatus.PENDING_APPROVAL,
    )

    # Ledger reference for the lock (available -> locked) posted at request
    # time, and the settlement/release reference posted at approve/reject
    # time. Both are here (not just on the wallet) so the full lifecycle of
    # one withdrawal is reconstructable from one row.
    lock_ledger_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    settlement_ledger_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # A plain string, not a UUID FK, because the reviewer may be an admin
    # user (a UUID as text) or a trusted internal service acting in an
    # automated-approval capacity (e.g. "service:risk-engine" in a later
    # phase) -- both are valid "who reviewed this" values.
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    withdrawal_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (CheckConstraint("amount > 0", name="ck_wallet_withdrawals_amount_positive"),)

import enum
import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EntryDirection(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class LedgerEntry(Base):
    """One line of a double-entry transaction.

    Convention used throughout this service (documented once, here, and
    nowhere else): CREDIT increases an account's balance, DEBIT decreases
    it. This is the intuitive "your balance went up/down" framing rather
    than traditional T-account asset/liability normal-balance conventions,
    and it is applied uniformly -- app.core.ledger_engine is the only code
    that is allowed to interpret direction, so there is exactly one place
    this convention could be gotten wrong.
    """

    __tablename__ = "ledger_entries"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    direction: Mapped[EntryDirection] = mapped_column(
        SAEnum(
            EntryDirection, name="ledger_entry_direction", values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
    )
    asset: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)

    # Account balance immediately after this entry was applied. Denormalized
    # onto the entry (rather than only trusting the account's cached
    # balance) so transaction history / statements can be rendered directly
    # from ledger_entries without recomputing a running total, and so
    # reconcile_account() has a per-entry checkpoint to bisect against if a
    # drift is ever detected instead of only a pass/fail on the whole account.
    balance_after: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)

    __table_args__ = (CheckConstraint("amount > 0", name="ck_ledger_entries_amount_positive"),)

    def __repr__(self) -> str:  # pragma: no cover - debug helper only
        return (
            f"<LedgerEntry id={self.id} txn={self.transaction_id} account={self.account_id} "
            f"{self.direction.value} {self.amount} {self.asset}>"
        )

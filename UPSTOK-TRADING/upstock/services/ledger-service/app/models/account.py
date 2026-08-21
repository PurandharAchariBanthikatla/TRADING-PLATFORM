import enum
import uuid
from decimal import Decimal

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OwnerType(str, enum.Enum):
    USER = "user"
    SYSTEM = "system"


class AccountType(str, enum.Enum):
    """Which bucket of a given (owner, asset) this row represents.

    USER_AVAILABLE / USER_LOCKED are the two balances every user-facing
    "available" vs "in open orders" split maps onto; PENDING is used for
    funds that are provisionally credited (e.g. an unconfirmed deposit)
    but not yet spendable or withdrawable.

    The SYSTEM_* types are the other leg of every transaction that moves
    value across the exchange boundary (deposits/withdrawals) or between
    users without a natural counter-account (fees). Nothing is ever
    conjured out of nothing -- every credit to a user account is balanced
    by a debit somewhere, and these are where those debits land.
    """

    USER_AVAILABLE = "user_available"
    USER_LOCKED = "user_locked"
    USER_PENDING = "user_pending"

    SYSTEM_RESERVE = "system_reserve"  # counter-account for deposits/withdrawals
    SYSTEM_FEE_REVENUE = "system_fee_revenue"  # where trading/withdrawal fees land
    SYSTEM_SUSPENSE = "system_suspense"  # temporary holding account; must trend to zero


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"

    owner_type: Mapped[OwnerType] = mapped_column(
        SAEnum(OwnerType, name="ledger_owner_type", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    # NULL for SYSTEM_* accounts (there is exactly one of each system
    # account per asset; see the partial unique index below).
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    asset: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "BTC", "USDT"
    account_type: Mapped[AccountType] = mapped_column(
        SAEnum(AccountType, name="ledger_account_type", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )

    # Cached balance, maintained transactionally by app.core.ledger_engine on
    # every post_transaction() call. This is a *cache* for fast reads -- the
    # source of truth is always the sum of ledger_entries for this account,
    # and reconcile_account() in ledger_engine.py exists specifically to
    # catch the two ever diverging (a bug, not an expected state).
    balance: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)

    __table_args__ = (
        # One row per (user, asset, account_type) for user-owned accounts.
        Index(
            "ux_ledger_accounts_user",
            "owner_id",
            "asset",
            "account_type",
            unique=True,
            postgresql_where=owner_id.isnot(None),
        ),
        # Exactly one row per (asset, account_type) among SYSTEM_* accounts
        # (owner_id is NULL for those).
        Index(
            "ux_ledger_accounts_system",
            "asset",
            "account_type",
            unique=True,
            postgresql_where=owner_id.is_(None),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper only
        return (
            f"<LedgerAccount id={self.id} owner={self.owner_type.value}:{self.owner_id} "
            f"asset={self.asset} type={self.account_type.value} balance={self.balance}>"
        )

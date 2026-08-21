import uuid

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Wallet(Base):
    """One row per (user, asset). Holds no balance itself -- balances live
    in ledger-service, this just records which three ledger accounts
    (available/locked/pending) belong to this wallet so wallet-service
    doesn't have to re-derive or guess ledger account ids on every call.
    """

    __tablename__ = "wallets"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asset: Mapped[str] = mapped_column(String(20), nullable=False)

    ledger_available_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ledger_locked_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ledger_pending_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    __table_args__ = (Index("ux_wallets_user_asset", "user_id", "asset", unique=True),)

    def __repr__(self) -> str:  # pragma: no cover - debug helper only
        return f"<Wallet id={self.id} user_id={self.user_id} asset={self.asset}>"

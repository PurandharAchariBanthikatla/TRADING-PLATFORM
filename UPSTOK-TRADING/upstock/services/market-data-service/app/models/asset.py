from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Asset(Base):
    """A currency/token the exchange knows about. Markets are always
    quoted as (base_asset, quote_asset) pairs referencing two of these.
    """

    __tablename__ = "assets"

    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Display/rounding precision for amounts of this asset shown standalone
    # (wallet balances etc). Per-market price/quantity precision on the
    # Market model is independent and is what governs order validation.
    decimals: Mapped[int] = mapped_column(Integer, nullable=False, default=8)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Asset {self.symbol}>"

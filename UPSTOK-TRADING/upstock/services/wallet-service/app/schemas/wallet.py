from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, field_validator

from app.models.deposit import DepositStatus
from app.models.transfer import TransferStatus
from app.models.withdrawal import WithdrawalStatus

# See services/ledger-service/app/schemas/ledger.py for why this exists:
# SQLAlchemy returns uuid.UUID objects for UUID columns and Pydantic v2's
# `str` type won't implicitly coerce them.
UUIDStr = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]


class WalletCreateRequest(BaseModel):
    asset: str = Field(min_length=1, max_length=20)

    @field_validator("asset")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class WalletResponse(BaseModel):
    id: UUIDStr
    user_id: UUIDStr
    asset: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WalletBalanceResponse(BaseModel):
    wallet_id: UUIDStr
    asset: str
    available: Decimal
    locked: Decimal
    pending: Decimal
    total: Decimal


class DepositRequest(BaseModel):
    asset: str = Field(min_length=1, max_length=20)
    amount: Decimal = Field(gt=0)
    reference: str = Field(min_length=1, max_length=255)
    metadata: dict = Field(default_factory=dict)

    @field_validator("asset")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class DepositResponse(BaseModel):
    id: UUIDStr
    wallet_id: UUIDStr
    reference: str
    asset: str
    amount: Decimal
    status: DepositStatus
    ledger_transaction_reference: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WithdrawalRequestCreate(BaseModel):
    asset: str = Field(min_length=1, max_length=20)
    amount: Decimal = Field(gt=0)
    destination: str = Field(min_length=1, max_length=500)
    reference: str = Field(min_length=1, max_length=255)
    metadata: dict = Field(default_factory=dict)

    @field_validator("asset")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class WithdrawalRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class WithdrawalResponse(BaseModel):
    id: UUIDStr
    wallet_id: UUIDStr
    reference: str
    asset: str
    amount: Decimal
    destination: str
    status: WithdrawalStatus
    lock_ledger_reference: str
    settlement_ledger_reference: str | None
    reviewed_by_user_id: UUIDStr | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InternalTransferRequest(BaseModel):
    to_user_id: str
    asset: str = Field(min_length=1, max_length=20)
    amount: Decimal = Field(gt=0)
    reference: str = Field(min_length=1, max_length=255)
    metadata: dict = Field(default_factory=dict)

    @field_validator("asset")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class InternalTransferResponse(BaseModel):
    id: UUIDStr
    from_wallet_id: UUIDStr
    to_wallet_id: UUIDStr
    reference: str
    asset: str
    amount: Decimal
    status: TransferStatus
    created_at: datetime

    model_config = {"from_attributes": True}

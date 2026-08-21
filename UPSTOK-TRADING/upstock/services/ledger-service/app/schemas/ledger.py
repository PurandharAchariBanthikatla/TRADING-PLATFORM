from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, field_validator

from app.models.account import AccountType, OwnerType
from app.models.entry import EntryDirection
from app.models.transaction import TransactionSourceType, TransactionStatus

# SQLAlchemy returns uuid.UUID objects for UUID columns; Pydantic v2's `str`
# type does not implicitly coerce a UUID into a str (only true str subtypes
# pass in lax mode), which made every response_model here reject FastAPI's
# own ORM objects. This normalizes UUID -> str (and leaves None alone) on
# every field annotated with it below, applied once instead of re-derived
# per field.
UUIDStr = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]


class AccountCreateRequest(BaseModel):
    """Get-or-create is intentional: callers (wallet service, admin tools)
    ask for "the USER_AVAILABLE BTC account for user X" without needing to
    know or care whether it already exists.
    """

    owner_type: OwnerType
    owner_id: str | None = None  # required for USER, must be None for SYSTEM
    asset: str = Field(min_length=1, max_length=20)
    account_type: AccountType

    @field_validator("asset")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class AccountResponse(BaseModel):
    id: UUIDStr
    owner_type: OwnerType
    owner_id: UUIDStr | None
    asset: str
    account_type: AccountType
    balance: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EntryInputSchema(BaseModel):
    account_id: UUIDStr
    direction: EntryDirection
    asset: str = Field(min_length=1, max_length=20)
    amount: Decimal = Field(gt=0)

    @field_validator("asset")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class PostTransactionRequest(BaseModel):
    reference: str = Field(min_length=1, max_length=255)
    source_type: TransactionSourceType
    entries: list[EntryInputSchema] = Field(min_length=2)
    description: str = ""
    metadata: dict = Field(default_factory=dict)


class EntryResponse(BaseModel):
    id: UUIDStr
    account_id: UUIDStr
    direction: EntryDirection
    asset: str
    amount: Decimal
    balance_after: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionResponse(BaseModel):
    id: UUIDStr
    reference: str
    source_type: TransactionSourceType
    status: TransactionStatus
    description: str
    metadata: dict = Field(validation_alias="transaction_metadata", serialization_alias="metadata")
    posted_at: datetime
    entries: list[EntryResponse] = []

    model_config = {"from_attributes": True, "populate_by_name": True}


class ReconciliationResponse(BaseModel):
    account_id: UUIDStr
    cached_balance: Decimal
    computed_balance: Decimal
    entry_count: int
    is_consistent: bool

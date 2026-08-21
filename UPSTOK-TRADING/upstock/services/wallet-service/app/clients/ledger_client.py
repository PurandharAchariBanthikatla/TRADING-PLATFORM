"""Client for calling ledger-service's accounting API.

This is the *only* place in wallet-service that talks to ledger-service.
Every wallet operation that moves value goes: wallet_engine -> this client
-> ledger-service's POST /ledger/transactions -> the double-entry engine.
wallet-service never touches ledger-service's database directly and never
computes a balance itself -- it always asks ledger-service, which is the
one source of truth for "how much does this account actually have".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import httpx

from app.core.config import settings


class LedgerClientError(Exception):
    """Base class for all ledger-service call failures."""


class LedgerInvariantError(LedgerClientError):
    """The proposed transaction was rejected as unbalanced/malformed (422)."""


class LedgerInsufficientBalanceError(LedgerClientError):
    """The proposed transaction would take a user account negative (409)."""


class LedgerAccountNotFoundError(LedgerClientError):
    """Referenced ledger account does not exist (404)."""


class LedgerUnavailableError(LedgerClientError):
    """Network failure or non-4xx-mapped error talking to ledger-service."""


@dataclass(frozen=True)
class LedgerAccountRef:
    id: str
    balance: Decimal


@dataclass(frozen=True)
class LedgerTransactionRef:
    id: str
    reference: str
    created: bool  # False if this was an idempotent replay of an existing transaction


class LedgerClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=settings.LEDGER_SERVICE_BASE_URL,
            timeout=settings.LEDGER_CLIENT_TIMEOUT_SECONDS,
            headers={
                "X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY,
                "X-Internal-Service-Name": settings.SERVICE_NAME,
            },
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_or_create_account(
        self, *, owner_type: str, owner_id: str | None, asset: str, account_type: str
    ) -> LedgerAccountRef:
        payload = {"owner_type": owner_type, "asset": asset, "account_type": account_type}
        if owner_id is not None:
            payload["owner_id"] = owner_id
        try:
            resp = await self._client.post("/ledger/accounts", json=payload)
        except httpx.HTTPError as exc:
            raise LedgerUnavailableError(str(exc)) from exc

        if resp.status_code != 200:
            raise LedgerUnavailableError(f"unexpected status {resp.status_code}: {resp.text}")

        body = resp.json()
        return LedgerAccountRef(id=body["id"], balance=Decimal(body["balance"]))

    async def get_account(self, account_id: str) -> LedgerAccountRef:
        try:
            resp = await self._client.get(f"/ledger/accounts/{account_id}")
        except httpx.HTTPError as exc:
            raise LedgerUnavailableError(str(exc)) from exc

        if resp.status_code == 404:
            raise LedgerAccountNotFoundError(account_id)
        if resp.status_code != 200:
            raise LedgerUnavailableError(f"unexpected status {resp.status_code}: {resp.text}")

        body = resp.json()
        return LedgerAccountRef(id=body["id"], balance=Decimal(body["balance"]))

    async def reconcile_account(self, account_id: str) -> dict:
        """Requires admin/service caller on ledger-service's side -- this
        client always calls as "service" via the shared internal key, so
        it's always permitted.
        """
        try:
            resp = await self._client.get(f"/ledger/accounts/{account_id}/reconcile")
        except httpx.HTTPError as exc:
            raise LedgerUnavailableError(str(exc)) from exc

        if resp.status_code == 404:
            raise LedgerAccountNotFoundError(account_id)
        if resp.status_code != 200:
            raise LedgerUnavailableError(f"unexpected status {resp.status_code}: {resp.text}")

        return resp.json()

    async def post_transaction(
        self,
        *,
        reference: str,
        source_type: str,
        entries: list[dict],
        description: str = "",
        metadata: dict | None = None,
    ) -> LedgerTransactionRef:
        """entries: list of {"account_id", "direction", "asset", "amount"} dicts.
        amount must be JSON-serializable (str or Decimal-as-str) -- callers
        should pass Decimal amounts as str(amount) to avoid float drift.
        """
        payload = {
            "reference": reference,
            "source_type": source_type,
            "entries": entries,
            "description": description,
            "metadata": metadata or {},
        }
        try:
            resp = await self._client.post("/ledger/transactions", json=payload)
        except httpx.HTTPError as exc:
            raise LedgerUnavailableError(str(exc)) from exc

        if resp.status_code == 422:
            raise LedgerInvariantError(resp.text)
        if resp.status_code == 409:
            raise LedgerInsufficientBalanceError(resp.text)
        if resp.status_code == 404:
            raise LedgerAccountNotFoundError(resp.text)
        if resp.status_code not in (200, 201):
            raise LedgerUnavailableError(f"unexpected status {resp.status_code}: {resp.text}")

        body = resp.json()
        # ledger-service's response doesn't distinguish "freshly posted" from
        # "idempotent replay" (its 201 covers both cases equally). That's
        # fine here: wallet_engine does its own idempotency check against
        # wallet-service's local tables *before* ever calling this client,
        # so this layer doesn't need to re-derive it.
        return LedgerTransactionRef(id=body["id"], reference=body["reference"], created=True)

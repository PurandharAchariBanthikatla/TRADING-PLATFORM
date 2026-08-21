import asyncio
from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_health_live(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_requires_auth(client):
    resp = await client.get("/api/v1/ledger/accounts/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_user_can_create_own_account(client, user_headers, user_id):
    resp = await client.post(
        "/api/v1/ledger/accounts",
        json={"owner_type": "user", "owner_id": user_id, "asset": "btc", "account_type": "user_available"},
        headers=user_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["asset"] == "BTC"  # normalized upper
    assert body["owner_id"] == user_id
    assert Decimal(body["balance"]) == Decimal("0")


@pytest.mark.asyncio
async def test_user_cannot_create_account_for_another_user(client, user_headers):
    resp = await client.post(
        "/api/v1/ledger/accounts",
        json={
            "owner_type": "user",
            "owner_id": "11111111-1111-1111-1111-111111111111",
            "asset": "BTC",
            "account_type": "user_available",
        },
        headers=user_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_user_cannot_create_system_account(client, user_headers):
    resp = await client.post(
        "/api/v1/ledger/accounts",
        json={"owner_type": "system", "asset": "BTC", "account_type": "system_reserve"},
        headers=user_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_post_balanced_transaction_and_user_can_read_own_balance(
    client, admin_headers, user_headers, user_id
):
    reserve = await client.post(
        "/api/v1/ledger/accounts",
        json={"owner_type": "system", "asset": "BTC", "account_type": "system_reserve"},
        headers=admin_headers,
    )
    assert reserve.status_code == 200
    reserve_id = reserve.json()["id"]

    user_acct = await client.post(
        "/api/v1/ledger/accounts",
        json={"owner_type": "user", "owner_id": user_id, "asset": "BTC", "account_type": "user_available"},
        headers=user_headers,
    )
    assert user_acct.status_code == 200
    user_acct_id = user_acct.json()["id"]

    txn = await client.post(
        "/api/v1/ledger/transactions",
        json={
            "reference": "api-deposit-1",
            "source_type": "deposit",
            "entries": [
                {"account_id": reserve_id, "direction": "debit", "asset": "BTC", "amount": "0.25"},
                {"account_id": user_acct_id, "direction": "credit", "asset": "BTC", "amount": "0.25"},
            ],
        },
        headers=admin_headers,
    )
    assert txn.status_code == 201
    assert len(txn.json()["entries"]) == 2

    mine = await client.get("/api/v1/ledger/accounts/me", headers=user_headers)
    assert mine.status_code == 200
    balances = {a["asset"]: a["balance"] for a in mine.json()}
    assert balances["BTC"] == "0.250000000000000000"

    # Admins can read any account, including ones they don't own.
    admin_view = await client.get(f"/api/v1/ledger/accounts/{user_acct_id}", headers=admin_headers)
    assert admin_view.status_code == 200


@pytest.mark.asyncio
async def test_regular_user_cannot_post_transactions(client, user_headers):
    resp = await client.post(
        "/api/v1/ledger/transactions",
        json={
            "reference": "should-fail",
            "source_type": "adjustment",
            "entries": [
                {
                    "account_id": "11111111-1111-1111-1111-111111111111",
                    "direction": "debit",
                    "asset": "BTC",
                    "amount": "1",
                },
                {
                    "account_id": "22222222-2222-2222-2222-222222222222",
                    "direction": "credit",
                    "asset": "BTC",
                    "amount": "1",
                },
            ],
        },
        headers=user_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_internal_service_key_can_post_transactions(client, service_headers, user_id):
    reserve = await client.post(
        "/api/v1/ledger/accounts",
        json={"owner_type": "system", "asset": "SOL", "account_type": "system_reserve"},
        headers=service_headers,
    )
    assert reserve.status_code == 200
    reserve_id = reserve.json()["id"]

    user_acct = await client.post(
        "/api/v1/ledger/accounts",
        json={"owner_type": "user", "owner_id": user_id, "asset": "SOL", "account_type": "user_available"},
        headers=service_headers,
    )
    assert user_acct.status_code == 200
    user_acct_id = user_acct.json()["id"]

    txn = await client.post(
        "/api/v1/ledger/transactions",
        json={
            "reference": "service-deposit-1",
            "source_type": "deposit",
            "entries": [
                {"account_id": reserve_id, "direction": "debit", "asset": "SOL", "amount": "3"},
                {"account_id": user_acct_id, "direction": "credit", "asset": "SOL", "amount": "3"},
            ],
        },
        headers=service_headers,
    )
    assert txn.status_code == 201


@pytest.mark.asyncio
async def test_wrong_internal_service_key_is_rejected(client):
    resp = await client.post(
        "/api/v1/ledger/accounts",
        json={"owner_type": "system", "asset": "SOL", "account_type": "system_reserve"},
        headers={"X-Internal-Service-Key": "not-the-real-key", "X-Internal-Service-Name": "wallet-service"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_get_or_create_account_does_not_500(client, admin_headers, user_id):
    """Two simultaneous get-or-create calls for the same (owner, asset,
    account_type) must both succeed and return the same account, not race
    into an unhandled unique-constraint IntegrityError (500). Regression
    test for a real bug caught via live end-to-end testing: the SELECT and
    INSERT here aren't atomic together, so a naive get-or-create loses this
    race under real concurrency even though single-request tests never see it.
    """
    payload = {"owner_type": "user", "owner_id": user_id, "asset": "RACE1", "account_type": "user_available"}

    results = await asyncio.gather(
        client.post("/api/v1/ledger/accounts", json=payload, headers=admin_headers),
        client.post("/api/v1/ledger/accounts", json=payload, headers=admin_headers),
        client.post("/api/v1/ledger/accounts", json=payload, headers=admin_headers),
    )

    for r in results:
        assert r.status_code == 200, r.text

    ids = {r.json()["id"] for r in results}
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_unbalanced_transaction_returns_422(client, admin_headers):
    reserve = await client.post(
        "/api/v1/ledger/accounts",
        json={"owner_type": "system", "asset": "ETH", "account_type": "system_reserve"},
        headers=admin_headers,
    )
    reserve_id = reserve.json()["id"]
    suspense = await client.post(
        "/api/v1/ledger/accounts",
        json={"owner_type": "system", "asset": "ETH", "account_type": "system_suspense"},
        headers=admin_headers,
    )
    suspense_id = suspense.json()["id"]

    resp = await client.post(
        "/api/v1/ledger/transactions",
        json={
            "reference": "unbalanced-api-1",
            "source_type": "adjustment",
            "entries": [
                {"account_id": reserve_id, "direction": "debit", "asset": "ETH", "amount": "1"},
                {"account_id": suspense_id, "direction": "credit", "asset": "ETH", "amount": "0.5"},
            ],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422

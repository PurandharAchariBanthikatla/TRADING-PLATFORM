import uuid
from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_health_live(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_wallet_and_zero_balance(client, user_headers, unique_asset):
    resp = await client.post("/api/v1/wallet/wallets", json={"asset": unique_asset}, headers=user_headers)
    assert resp.status_code == 200
    wallet = resp.json()
    assert wallet["asset"] == unique_asset

    balance = await client.get(f"/api/v1/wallet/wallets/{wallet['id']}/balance", headers=user_headers)
    assert balance.status_code == 200
    body = balance.json()
    assert Decimal(body["available"]) == 0
    assert Decimal(body["locked"]) == 0
    assert Decimal(body["pending"]) == 0
    assert Decimal(body["total"]) == 0


@pytest.mark.asyncio
async def test_deposit_credits_available_balance(client, user_headers, unique_asset):
    ref = f"dep-{uuid.uuid4()}"
    resp = await client.post(
        "/api/v1/wallet/deposits",
        json={"asset": unique_asset, "amount": "5.5", "reference": ref},
        headers=user_headers,
    )
    assert resp.status_code == 201
    deposit = resp.json()
    assert deposit["status"] == "confirmed"

    wallets = await client.get("/api/v1/wallet/wallets/me", headers=user_headers)
    wallet_id = next(w["id"] for w in wallets.json() if w["asset"] == unique_asset)

    balance = await client.get(f"/api/v1/wallet/wallets/{wallet_id}/balance", headers=user_headers)
    assert balance.json()["available"] == "5.500000000000000000"


@pytest.mark.asyncio
async def test_deposit_is_idempotent_by_reference(client, user_headers, unique_asset):
    ref = f"dep-idem-{uuid.uuid4()}"
    payload = {"asset": unique_asset, "amount": "3", "reference": ref}

    first = await client.post("/api/v1/wallet/deposits", json=payload, headers=user_headers)
    second = await client.post("/api/v1/wallet/deposits", json=payload, headers=user_headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    wallets = await client.get("/api/v1/wallet/wallets/me", headers=user_headers)
    wallet_id = next(w["id"] for w in wallets.json() if w["asset"] == unique_asset)
    balance = await client.get(f"/api/v1/wallet/wallets/{wallet_id}/balance", headers=user_headers)
    # Exactly one deposit's worth, not two.
    assert balance.json()["available"] == "3.000000000000000000"


@pytest.mark.asyncio
async def test_withdrawal_locks_funds_and_requires_approval(
    client, user_headers, admin_headers, unique_asset
):
    await client.post(
        "/api/v1/wallet/deposits",
        json={"asset": unique_asset, "amount": "10", "reference": f"dep-{uuid.uuid4()}"},
        headers=user_headers,
    )
    wallets = await client.get("/api/v1/wallet/wallets/me", headers=user_headers)
    wallet_id = next(w["id"] for w in wallets.json() if w["asset"] == unique_asset)

    withdraw_ref = f"wd-{uuid.uuid4()}"
    resp = await client.post(
        "/api/v1/wallet/withdrawals",
        json={
            "asset": unique_asset,
            "amount": "4",
            "destination": "paper-address-1",
            "reference": withdraw_ref,
        },
        headers=user_headers,
    )
    assert resp.status_code == 201
    withdrawal = resp.json()
    assert withdrawal["status"] == "pending_approval"

    # Funds are locked immediately, before any admin action.
    balance = await client.get(f"/api/v1/wallet/wallets/{wallet_id}/balance", headers=user_headers)
    body = balance.json()
    assert body["available"] == "6.000000000000000000"
    assert body["locked"] == "4.000000000000000000"
    assert body["total"] == "10.000000000000000000"

    approve = await client.post(
        f"/api/v1/wallet/withdrawals/{withdrawal['id']}/approve", headers=admin_headers
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "completed"

    balance_after = (
        await client.get(f"/api/v1/wallet/wallets/{wallet_id}/balance", headers=user_headers)
    ).json()
    assert balance_after["available"] == "6.000000000000000000"
    assert Decimal(balance_after["locked"]) == 0
    assert balance_after["total"] == "6.000000000000000000"


@pytest.mark.asyncio
async def test_rejected_withdrawal_releases_lock(client, user_headers, admin_headers, unique_asset):
    await client.post(
        "/api/v1/wallet/deposits",
        json={"asset": unique_asset, "amount": "10", "reference": f"dep-{uuid.uuid4()}"},
        headers=user_headers,
    )
    wallets = await client.get("/api/v1/wallet/wallets/me", headers=user_headers)
    wallet_id = next(w["id"] for w in wallets.json() if w["asset"] == unique_asset)

    resp = await client.post(
        "/api/v1/wallet/withdrawals",
        json={
            "asset": unique_asset,
            "amount": "4",
            "destination": "paper-address-1",
            "reference": f"wd-{uuid.uuid4()}",
        },
        headers=user_headers,
    )
    withdrawal = resp.json()

    reject = await client.post(
        f"/api/v1/wallet/withdrawals/{withdrawal['id']}/reject",
        json={"reason": "manual review failed"},
        headers=admin_headers,
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"
    assert reject.json()["rejection_reason"] == "manual review failed"

    balance = (await client.get(f"/api/v1/wallet/wallets/{wallet_id}/balance", headers=user_headers)).json()
    # Funds are fully back in available, none lost, none still locked.
    assert balance["available"] == "10.000000000000000000"
    assert Decimal(balance["locked"]) == 0


@pytest.mark.asyncio
async def test_cannot_approve_same_withdrawal_twice(client, user_headers, admin_headers, unique_asset):
    await client.post(
        "/api/v1/wallet/deposits",
        json={"asset": unique_asset, "amount": "10", "reference": f"dep-{uuid.uuid4()}"},
        headers=user_headers,
    )
    resp = await client.post(
        "/api/v1/wallet/withdrawals",
        json={"asset": unique_asset, "amount": "2", "destination": "x", "reference": f"wd-{uuid.uuid4()}"},
        headers=user_headers,
    )
    withdrawal_id = resp.json()["id"]

    first = await client.post(f"/api/v1/wallet/withdrawals/{withdrawal_id}/approve", headers=admin_headers)
    second = await client.post(f"/api/v1/wallet/withdrawals/{withdrawal_id}/approve", headers=admin_headers)

    assert first.status_code == 200
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_withdrawal_exceeding_available_balance_is_rejected(client, user_headers, unique_asset):
    await client.post(
        "/api/v1/wallet/deposits",
        json={"asset": unique_asset, "amount": "1", "reference": f"dep-{uuid.uuid4()}"},
        headers=user_headers,
    )
    resp = await client.post(
        "/api/v1/wallet/withdrawals",
        json={"asset": unique_asset, "amount": "1000", "destination": "x", "reference": f"wd-{uuid.uuid4()}"},
        headers=user_headers,
    )
    assert resp.status_code == 409  # ledger's insufficient-balance error, translated


@pytest.mark.asyncio
async def test_withdrawal_over_per_transaction_limit_is_rejected(client, user_headers, unique_asset):
    await client.post(
        "/api/v1/wallet/deposits",
        json={"asset": unique_asset, "amount": "999999", "reference": f"dep-{uuid.uuid4()}"},
        headers=user_headers,
    )
    resp = await client.post(
        "/api/v1/wallet/withdrawals",
        json={
            "asset": unique_asset,
            "amount": "50000",
            "destination": "x",
            "reference": f"wd-{uuid.uuid4()}",
        },
        headers=user_headers,
    )
    assert resp.status_code == 422
    assert "per-transaction" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_internal_transfer_moves_funds_between_users(
    client, user_headers, other_user_id, other_user_headers, unique_asset
):
    await client.post(
        "/api/v1/wallet/deposits",
        json={"asset": unique_asset, "amount": "10", "reference": f"dep-{uuid.uuid4()}"},
        headers=user_headers,
    )

    resp = await client.post(
        "/api/v1/wallet/transfers",
        json={
            "to_user_id": other_user_id,
            "asset": unique_asset,
            "amount": "3",
            "reference": f"xfer-{uuid.uuid4()}",
        },
        headers=user_headers,
    )
    assert resp.status_code == 201

    sender_wallets = await client.get("/api/v1/wallet/wallets/me", headers=user_headers)
    sender_wallet_id = next(w["id"] for w in sender_wallets.json() if w["asset"] == unique_asset)
    sender_balance = (
        await client.get(f"/api/v1/wallet/wallets/{sender_wallet_id}/balance", headers=user_headers)
    ).json()
    assert sender_balance["available"] == "7.000000000000000000"

    receiver_wallets = await client.get("/api/v1/wallet/wallets/me", headers=other_user_headers)
    receiver_wallet_id = next(w["id"] for w in receiver_wallets.json() if w["asset"] == unique_asset)
    receiver_balance = (
        await client.get(f"/api/v1/wallet/wallets/{receiver_wallet_id}/balance", headers=other_user_headers)
    ).json()
    assert receiver_balance["available"] == "3.000000000000000000"


@pytest.mark.asyncio
async def test_user_cannot_view_another_users_wallet(client, user_headers, other_user_headers, unique_asset):
    create = await client.post("/api/v1/wallet/wallets", json={"asset": unique_asset}, headers=user_headers)
    wallet_id = create.json()["id"]

    resp = await client.get(f"/api/v1/wallet/wallets/{wallet_id}/balance", headers=other_user_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_requires_auth(client):
    resp = await client.get("/api/v1/wallet/wallets/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_regular_user_cannot_approve_withdrawals(client, user_headers, unique_asset):
    await client.post(
        "/api/v1/wallet/deposits",
        json={"asset": unique_asset, "amount": "10", "reference": f"dep-{uuid.uuid4()}"},
        headers=user_headers,
    )
    resp = await client.post(
        "/api/v1/wallet/withdrawals",
        json={"asset": unique_asset, "amount": "1", "destination": "x", "reference": f"wd-{uuid.uuid4()}"},
        headers=user_headers,
    )
    withdrawal_id = resp.json()["id"]

    approve = await client.post(f"/api/v1/wallet/withdrawals/{withdrawal_id}/approve", headers=user_headers)
    assert approve.status_code == 403

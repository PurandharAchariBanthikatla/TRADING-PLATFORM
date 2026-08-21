import pytest

from app.core.config import settings

pytestmark = pytest.mark.asyncio

VALID_PASSWORD = "CorrectHorse9"


async def _register(client, email, password=VALID_PASSWORD, display_name="Test Trader"):
    return await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )


async def _login(client, email, password=VALID_PASSWORD):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_register_success(client, unique_email):
    resp = await _register(client, unique_email)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == unique_email
    assert body["role"] == "user"
    assert "hashed_password" not in body


async def test_register_rejects_weak_password(client, unique_email):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "password": "alllowercase1", "display_name": "Trader"},
    )
    assert resp.status_code == 422


async def test_register_duplicate_email_returns_409(client, unique_email):
    first = await _register(client, unique_email)
    assert first.status_code == 201

    second = await _register(client, unique_email)
    assert second.status_code == 409


async def test_login_success_returns_token_pair(client, unique_email):
    await _register(client, unique_email)
    resp = await _login(client, unique_email)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


async def test_login_wrong_password_returns_401(client, unique_email):
    await _register(client, unique_email)
    resp = await _login(client, unique_email, password="TotallyWrong1")
    assert resp.status_code == 401


async def test_login_unknown_email_returns_401_not_404(client, unique_email):
    # Must not leak whether the account exists.
    resp = await _login(client, unique_email)
    assert resp.status_code == 401


async def test_login_rate_limited_after_max_attempts(client, unique_email):
    await _register(client, unique_email)
    for _ in range(settings.RATE_LIMIT_LOGIN_ATTEMPTS):
        resp = await _login(client, unique_email, password="wrong-password")
        assert resp.status_code == 401

    blocked = await _login(client, unique_email, password="wrong-password")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


async def test_me_requires_auth(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user_with_valid_token(client, unique_email):
    await _register(client, unique_email)
    login_resp = await _login(client, unique_email)
    access_token = login_resp.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == unique_email


async def test_refresh_rotates_token_and_invalidates_old_one(client, unique_email):
    await _register(client, unique_email)
    login_resp = await _login(client, unique_email)
    old_refresh = login_resp.json()["refresh_token"]

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refreshed.status_code == 200
    new_refresh = refreshed.json()["refresh_token"]
    assert new_refresh != old_refresh

    # The old refresh token must now be dead (rotation / reuse detection).
    reuse_attempt = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse_attempt.status_code == 401


async def test_logout_revokes_refresh_token(client, unique_email):
    await _register(client, unique_email)
    login_resp = await _login(client, unique_email)
    refresh_token = login_resp.json()["refresh_token"]

    logout_resp = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 204

    reuse_attempt = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_attempt.status_code == 401

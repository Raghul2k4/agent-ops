"""Integration tests for authentication, sessions and CSRF protection."""

from __future__ import annotations

import pytest

from app.core.security import CSRF_HEADER_NAME, SESSION_COOKIE_NAME

pytestmark = pytest.mark.integration

REGISTRATION = {
    "email": "engineer@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "Priya Engineer",
}


class TestRegistration:
    async def test_register_creates_user_and_session(self, client) -> None:
        response = await client.post("/api/v1/auth/register", json=REGISTRATION)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["user"]["email"] == "engineer@example.com"
        assert body["user"]["display_name"] == "Priya Engineer"
        assert "password" not in response.text
        assert SESSION_COOKIE_NAME in client.cookies

    async def test_duplicate_email_is_rejected(self, client) -> None:
        await client.post("/api/v1/auth/register", json=REGISTRATION)
        response = await client.post("/api/v1/auth/register", json=REGISTRATION)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"

    async def test_weak_password_is_rejected(self, client) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "weak@example.com", "password": "short", "display_name": "Weak"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_invalid_email_is_rejected(self, client) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "Sup3rSecret!2026", "display_name": "X"},
        )
        assert response.status_code == 422


class TestLogin:
    async def test_login_succeeds_with_correct_credentials(self, client) -> None:
        await client.post("/api/v1/auth/register", json=REGISTRATION)
        await client.post("/api/v1/auth/logout")
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTRATION["email"], "password": REGISTRATION["password"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["user"]["email"] == REGISTRATION["email"]

    async def test_login_fails_with_wrong_password(self, client) -> None:
        await client.post("/api/v1/auth/register", json=REGISTRATION)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTRATION["email"], "password": "WrongPassword!1"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    async def test_unknown_account_is_indistinguishable(self, client) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "WrongPassword!1"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Invalid email address or password."


class TestSessionAndCsrf:
    async def test_me_requires_authentication(self, client) -> None:
        response = await client.get("/api/v1/me")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    async def test_me_returns_the_current_user(self, client) -> None:
        await client.post("/api/v1/auth/register", json=REGISTRATION)
        response = await client.get("/api/v1/me")
        assert response.status_code == 200
        assert response.json()["user"]["email"] == REGISTRATION["email"]
        assert response.json()["workspaces"] == []

    async def test_mutation_without_csrf_header_is_rejected(self, client) -> None:
        await client.post("/api/v1/auth/register", json=REGISTRATION)
        response = await client.post(
            "/api/v1/workspaces",
            json={"name": "Unauthorised Workspace"},
            headers={CSRF_HEADER_NAME: ""},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    async def test_mutation_with_tampered_csrf_is_rejected(self, client) -> None:
        await client.post("/api/v1/auth/register", json=REGISTRATION)
        response = await client.post(
            "/api/v1/workspaces",
            json={"name": "Tampered Workspace"},
            headers={CSRF_HEADER_NAME: "forged-token"},
        )
        assert response.status_code == 403

    async def test_logout_revokes_the_session(self, client) -> None:
        await client.post("/api/v1/auth/register", json=REGISTRATION)
        logout = await client.post("/api/v1/auth/logout")
        assert logout.status_code == 204
        me = await client.get("/api/v1/me")
        assert me.status_code == 401

    async def test_csrf_rotation_issues_a_new_token(self, client) -> None:
        await client.post("/api/v1/auth/register", json=REGISTRATION)
        old = client.cookies.get("agentops_csrf")
        response = await client.post("/api/v1/auth/csrf")
        assert response.status_code == 200
        new = response.json()["csrf_token"]
        assert new != old
        assert client.cookies.get("agentops_csrf") == new

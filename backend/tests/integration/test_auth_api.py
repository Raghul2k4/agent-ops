"""Integration tests for bearer authentication.

These run against the real database and the real FastAPI application. The
development issuer is used for the local-mode tests; the Supabase path is
exercised with a stub verifier so profile provisioning is covered without a
hosted project.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.auth.claims import TokenClaims, TokenError
from app.auth.issuer import issue_local_token
from app.auth.verify import set_verifier
from app.core.config import settings

pytestmark = pytest.mark.integration

REGISTRATION = {
    "email": "engineer@example.com",
    "password": "Sup3rSecret!2026",
    "display_name": "Priya Engineer",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _StaticVerifier:
    """Accepts one fixed token and returns fixed claims."""

    def __init__(self, claims: TokenClaims) -> None:
        self._claims = claims

    async def verify(self, token: str) -> TokenClaims:
        if token != "stub-access-token":
            raise TokenError("unexpected token")
        return self._claims


def _claims(subject: uuid.UUID, *, email: str | None = "supa@example.com") -> TokenClaims:
    return TokenClaims(
        subject=subject,
        audience=("authenticated",),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        issued_at=datetime.now(UTC),
        issuer="https://project.supabase.co/auth/v1",
        email=email,
        role="authenticated",
        display_name="Supabase User",
    )


class TestAuthMode:
    async def test_local_mode_is_reported(self, client) -> None:
        response = await client.get("/api/v1/auth/mode")
        assert response.status_code == 200
        body = response.json()
        assert body["auth_mode"] == "local"
        assert body["local_sign_in_enabled"] is True
        assert body["supabase_url"] is None


class TestRegistration:
    async def test_register_returns_a_bearer_token(self, client) -> None:
        response = await client.post("/api/v1/auth/register", json=REGISTRATION)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["token_type"] == "bearer"
        assert len(body["access_token"].split(".")) == 3
        assert body["user"]["email"] == "engineer@example.com"
        assert body["user"]["display_name"] == "Priya Engineer"
        assert body["workspaces"] == []
        assert "password" not in response.text
        assert "set-cookie" not in response.headers

    async def test_duplicate_email_is_rejected(self, client, register_user) -> None:
        await register_user(REGISTRATION)
        response = await client.post("/api/v1/auth/register", json=REGISTRATION)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"

    async def test_weak_password_reports_the_policy(self, client) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "weak@example.com", "password": "alllowercase", "display_name": "Weak"},
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert error["details"]["password_policy"]


class TestLogin:
    async def test_login_issues_a_token(self, client, register_user) -> None:
        await register_user(REGISTRATION)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTRATION["email"], "password": REGISTRATION["password"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["access_token"]

    async def test_wrong_password_and_unknown_email_are_indistinguishable(
        self, client, register_user
    ) -> None:
        await register_user(REGISTRATION)
        wrong_password = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTRATION["email"], "password": "WrongPassword!2026"},
        )
        unknown_email = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": REGISTRATION["password"]},
        )
        assert wrong_password.status_code == 401
        assert unknown_email.status_code == 401
        assert wrong_password.json()["error"]["message"] == unknown_email.json()["error"]["message"]


class TestProtectedEndpoints:
    async def test_missing_token_is_rejected(self, client) -> None:
        response = await client.get("/api/v1/me")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    async def test_non_bearer_scheme_is_rejected(self, client) -> None:
        response = await client.get("/api/v1/me", headers={"Authorization": "Token abc"})
        assert response.status_code == 401

    async def test_garbage_token_is_rejected(self, client) -> None:
        response = await client.get("/api/v1/me", headers=_auth("not-a-jwt"))
        assert response.status_code == 401

    async def test_unknown_api_key_is_rejected(self, client) -> None:
        response = await client.get("/api/v1/me", headers=_auth("agoa_not-a-real-key"))
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    async def test_expired_token_is_rejected(self, client, register_user) -> None:
        auth = await register_user(REGISTRATION)
        expired, _ = issue_local_token(
            subject=uuid.UUID(auth["user"]["id"]),
            email=REGISTRATION["email"],
            ttl_minutes=-1,
        )
        response = await client.get("/api/v1/me", headers=_auth(expired))
        assert response.status_code == 401

    async def test_valid_token_returns_the_profile(self, client, register_user) -> None:
        auth = await register_user(REGISTRATION)
        response = await client.get("/api/v1/me", headers=_auth(auth["access_token"]))
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["id"] == auth["user"]["id"]
        assert body["user"]["email"] == REGISTRATION["email"]
        assert body["workspaces"] == []


class TestLogout:
    async def test_logout_records_an_audit_event(self, client, db_session, register_user) -> None:
        auth = await register_user(REGISTRATION)
        response = await client.post("/api/v1/auth/logout", headers=_auth(auth["access_token"]))
        assert response.status_code == 204

        actions = (
            (await db_session.execute(text("select action from app.audit_events"))).scalars().all()
        )
        assert "auth.register" in actions
        assert "auth.logout" in actions


class TestSupabaseMode:
    async def test_local_sign_in_is_disabled(self, client, monkeypatch) -> None:
        monkeypatch.setattr(settings, "auth_mode", "supabase")

        registration = await client.post("/api/v1/auth/register", json=REGISTRATION)
        assert registration.status_code == 403
        assert registration.json()["error"]["code"] == "PERMISSION_DENIED"

        mode = await client.get("/api/v1/auth/mode")
        assert mode.json()["auth_mode"] == "supabase"
        assert mode.json()["local_sign_in_enabled"] is False

    async def test_token_provisions_the_profile_once(self, client, db_session, monkeypatch) -> None:
        monkeypatch.setattr(settings, "auth_mode", "supabase")
        subject = uuid.uuid4()
        # Supabase Auth owns `auth.users`; the identity row always exists before
        # its first API call, and `app.profiles` references it.
        await db_session.execute(
            text("insert into auth.users (id, email) values (:id, :email)"),
            {"id": subject, "email": "supa@example.com"},
        )
        await db_session.commit()
        set_verifier(_StaticVerifier(_claims(subject)))

        first = await client.get("/api/v1/me", headers=_auth("stub-access-token"))
        second = await client.get("/api/v1/me", headers=_auth("stub-access-token"))

        assert first.status_code == 200, first.text
        assert first.json()["user"]["id"] == str(subject)
        assert first.json()["user"]["email"] == "supa@example.com"
        assert second.json()["user"]["id"] == str(subject)

        profiles = await db_session.scalar(text("select count(*) from app.profiles"))
        assert profiles == 1

    async def test_identity_without_email_is_rejected(self, client, monkeypatch) -> None:
        monkeypatch.setattr(settings, "auth_mode", "supabase")
        set_verifier(_StaticVerifier(_claims(uuid.uuid4(), email=None)))

        response = await client.get("/api/v1/me", headers=_auth("stub-access-token"))
        assert response.status_code == 401
        assert "email" in response.json()["error"]["message"].lower()

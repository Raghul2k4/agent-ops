"""Unit tests for token verification and auth-mode configuration.

The Supabase verifier is exercised against a freshly generated RSA key pair and
an in-process JWKS document, so the JWKS code path (key selection, caching,
rotation, algorithm allow-list) is covered without a hosted project or network
access.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from app.auth.claims import TokenClaims, TokenError
from app.auth.issuer import LOCAL_AUDIENCE, issue_local_token
from app.auth.verify import LocalTokenVerifier, SupabaseTokenVerifier
from app.core.config import Settings, settings

SUPABASE_ISSUER = "https://project.supabase.co/auth/v1"
SUPABASE_AUDIENCE = "authenticated"


def _local_verifier() -> LocalTokenVerifier:
    return LocalTokenVerifier(
        secret=settings.local_jwt_secret,
        issuer=settings.local_jwt_issuer,
        audience=LOCAL_AUDIENCE,
    )


def _rsa_keypair(kid: str = "test-key-1"):  # type: ignore[no-untyped-def]
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private_key, jwk  # type: ignore[return-value]


def _supabase_token(private_key, *, kid: str = "test-key-1", **overrides) -> str:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "aud": SUPABASE_AUDIENCE,
        "iss": SUPABASE_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "email": "user@example.com",
        "role": "authenticated",
    }
    payload.update(overrides)
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


def _supabase_verifier(jwk: dict, *, fetcher=None) -> SupabaseTokenVerifier:  # type: ignore[no-untyped-def]
    async def default_fetcher(url: str) -> dict:
        return {"keys": [jwk]}

    return SupabaseTokenVerifier(
        jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
        issuer=SUPABASE_ISSUER,
        audience=SUPABASE_AUDIENCE,
        fetcher=fetcher or default_fetcher,
    )


class TestLocalTokens:
    async def test_roundtrip_preserves_identity(self) -> None:
        subject = uuid.uuid4()
        token, expires_at = issue_local_token(subject=subject, email="dev@example.com")

        claims = await _local_verifier().verify(token)

        assert claims.subject == subject
        assert claims.email == "dev@example.com"
        assert claims.audience == (LOCAL_AUDIENCE,)
        assert claims.issuer == settings.local_jwt_issuer
        assert abs((claims.expires_at - expires_at).total_seconds()) < 2

    async def test_expired_token_is_rejected(self) -> None:
        token, _ = issue_local_token(subject=uuid.uuid4(), email="dev@example.com", ttl_minutes=-5)
        with pytest.raises(TokenError):
            await _local_verifier().verify(token)

    async def test_wrong_issuer_is_rejected(self) -> None:
        token, _ = issue_local_token(subject=uuid.uuid4(), email="dev@example.com")
        verifier = LocalTokenVerifier(
            secret=settings.local_jwt_secret,
            issuer="https://someone-else.example",
            audience=LOCAL_AUDIENCE,
        )
        with pytest.raises(TokenError):
            await verifier.verify(token)

    async def test_wrong_audience_is_rejected(self) -> None:
        token, _ = issue_local_token(subject=uuid.uuid4(), email="dev@example.com")
        verifier = LocalTokenVerifier(
            secret=settings.local_jwt_secret,
            issuer=settings.local_jwt_issuer,
            audience="service_role",
        )
        with pytest.raises(TokenError):
            await verifier.verify(token)

    async def test_tampered_signature_is_rejected(self) -> None:
        token, _ = issue_local_token(subject=uuid.uuid4(), email="dev@example.com")
        header, payload, signature = token.split(".")
        # Flip a signature character for certain: replacing the first character
        # with a fixed letter is a no-op whenever the signature already starts
        # with that letter, which would make this test pass for the wrong reason.
        replacement = "B" if signature[0] == "A" else "A"
        tampered = f"{header}.{payload}.{replacement}{signature[1:]}"
        with pytest.raises(TokenError):
            await _local_verifier().verify(tampered)

    async def test_token_signed_with_another_secret_is_rejected(self) -> None:
        now = datetime.now(UTC)
        forged = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "aud": LOCAL_AUDIENCE,
                "iss": settings.local_jwt_issuer,
                "exp": int((now + timedelta(minutes=5)).timestamp()),
            },
            "a-different-secret-that-is-long-enough-for-hs256",
            algorithm="HS256",
        )
        with pytest.raises(TokenError):
            await _local_verifier().verify(forged)


class TestSupabaseVerifier:
    async def test_valid_token_is_accepted_and_keys_are_cached(self) -> None:
        private_key, jwk = _rsa_keypair()
        calls = 0

        async def fetcher(url: str) -> dict:
            nonlocal calls
            calls += 1
            return {"keys": [jwk]}

        verifier = _supabase_verifier(jwk, fetcher=fetcher)
        token = _supabase_token(private_key)

        claims = await verifier.verify(token)
        await verifier.verify(token)

        assert calls == 1, "the JWKS document must be cached between requests"
        assert claims.email == "user@example.com"
        assert claims.audience == (SUPABASE_AUDIENCE,)
        assert claims.issuer == SUPABASE_ISSUER

    async def test_expired_token_is_rejected(self) -> None:
        private_key, jwk = _rsa_keypair()
        past = int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())
        token = _supabase_token(private_key, exp=past)
        with pytest.raises(TokenError):
            await _supabase_verifier(jwk).verify(token)

    async def test_wrong_issuer_is_rejected(self) -> None:
        private_key, jwk = _rsa_keypair()
        token = _supabase_token(private_key, iss="https://attacker.example/auth/v1")
        with pytest.raises(TokenError):
            await _supabase_verifier(jwk).verify(token)

    async def test_wrong_audience_is_rejected(self) -> None:
        private_key, jwk = _rsa_keypair()
        token = _supabase_token(private_key, aud="anon")
        with pytest.raises(TokenError):
            await _supabase_verifier(jwk).verify(token)

    async def test_symmetric_token_is_rejected_without_fetching_keys(self) -> None:
        _, jwk = _rsa_keypair()
        fetched = False

        async def fetcher(url: str) -> dict:
            nonlocal fetched
            fetched = True
            return {"keys": [jwk]}

        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "aud": SUPABASE_AUDIENCE,
                "iss": SUPABASE_ISSUER,
                "exp": int((now + timedelta(minutes=5)).timestamp()),
            },
            "shared-secret-must-never-verify-supabase-tokens",
            algorithm="HS256",
        )
        with pytest.raises(TokenError):
            await _supabase_verifier(jwk, fetcher=fetcher).verify(token)
        assert fetched is False

    async def test_key_rotation_refreshes_the_cache_once(self) -> None:
        old_private, old_jwk = _rsa_keypair("old-key")
        new_private, new_jwk = _rsa_keypair("new-key")
        documents = [{"keys": [old_jwk]}, {"keys": [old_jwk, new_jwk]}]
        calls = 0

        async def fetcher(url: str) -> dict:
            nonlocal calls
            calls += 1
            return documents[min(calls - 1, len(documents) - 1)]

        verifier = _supabase_verifier(old_jwk, fetcher=fetcher)
        await verifier.verify(_supabase_token(old_private, kid="old-key"))

        claims = await verifier.verify(_supabase_token(new_private, kid="new-key"))

        assert claims.issuer == SUPABASE_ISSUER
        assert calls == 2, "an unknown kid must trigger exactly one refresh"

    async def test_unknown_kid_is_rejected_after_refresh(self) -> None:
        private_key, jwk = _rsa_keypair()
        calls = 0

        async def fetcher(url: str) -> dict:
            nonlocal calls
            calls += 1
            return {"keys": [jwk]}

        verifier = _supabase_verifier(jwk, fetcher=fetcher)
        token = _supabase_token(private_key, kid="ghost-key")
        with pytest.raises(TokenError):
            await verifier.verify(token)
        assert calls == 2

    async def test_jwks_outage_is_a_controlled_failure(self) -> None:
        _, jwk = _rsa_keypair()

        async def fetcher(url: str) -> dict:
            raise httpx.ConnectError("no route to host")

        with pytest.raises(TokenError):
            await _supabase_verifier(jwk, fetcher=fetcher).verify(
                _supabase_token(_rsa_keypair()[0])
            )

    async def test_malformed_token_is_rejected(self) -> None:
        _, jwk = _rsa_keypair()
        with pytest.raises(TokenError):
            await _supabase_verifier(jwk).verify("not-a-jwt")


class TestClaims:
    def test_non_uuid_subject_is_rejected(self) -> None:
        with pytest.raises(TokenError):
            TokenClaims.from_payload(
                {"sub": "not-a-uuid", "aud": "authenticated", "exp": 9999999999}
            )

    def test_missing_expiry_is_rejected(self) -> None:
        with pytest.raises(TokenError):
            TokenClaims.from_payload({"sub": str(uuid.uuid4()), "aud": "authenticated"})

    def test_audience_list_is_normalised(self) -> None:
        claims = TokenClaims.from_payload(
            {
                "sub": str(uuid.uuid4()),
                "aud": ["authenticated", "agentops"],
                "exp": 9999999999,
                "user_metadata": {"full_name": "  Ada Lovelace  "},
            }
        )
        assert claims.audience == ("authenticated", "agentops")
        assert claims.display_name == "Ada Lovelace"


class TestAuthSettings:
    def test_local_auth_is_rejected_in_production(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, environment="production", auth_mode="local")

    def test_local_auth_is_rejected_in_staging(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, environment="staging", auth_mode="local")

    def test_supabase_mode_requires_a_project_url(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, auth_mode="supabase")

    def test_supabase_mode_derives_jwks_and_issuer(self) -> None:
        configured = Settings(
            _env_file=None,
            auth_mode="supabase",
            supabase_url="https://project.supabase.co",
        )
        assert configured.jwks_url == ("https://project.supabase.co/auth/v1/.well-known/jwks.json")
        assert configured.jwt_issuer == "https://project.supabase.co/auth/v1"

    def test_short_local_secret_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, auth_mode="local", local_jwt_secret="too-short")

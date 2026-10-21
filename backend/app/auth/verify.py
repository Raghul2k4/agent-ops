"""Access-token verification.

Two issuers, one interface:

* ``supabase`` - hosted Supabase Auth. Tokens are verified cryptographically
  against the project's JWKS (never against a shared secret), checking
  signature, ``iss``, ``aud`` and ``exp``.
* ``local`` - development/test only. Tokens are issued and verified by this
  process with an HS256 secret. The mode is rejected outside development/test
  by ``Settings._validate_auth`` and again at issue time.

The rest of the application only depends on ``TokenVerifier.verify``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, cast

import httpx
import jwt

from app.auth.claims import TokenClaims, TokenError
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Supabase currently signs with ES256 or RS256; EdDSA is accepted for forward
# compatibility. Symmetric algorithms are never accepted for Supabase tokens.
SUPABASE_ALLOWED_ALGORITHMS = frozenset({"RS256", "ES256", "EdDSA"})

JwksFetcher = Callable[[str], Awaitable[Mapping[str, Any]]]


async def _default_jwks_fetcher(url: str) -> Mapping[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):  # pragma: no cover - defensive
            raise TokenError("The JWKS endpoint returned an unexpected payload.")
        return cast(Mapping[str, Any], payload)


class TokenVerifier(Protocol):
    """Verifies a bearer token and returns its claims."""

    async def verify(self, token: str) -> TokenClaims: ...


class LocalTokenVerifier:
    """Verifies development tokens issued by ``app.auth.issuer``."""

    def __init__(self, *, secret: str, issuer: str, audience: str) -> None:
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    async def verify(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenError(f"local token rejected: {type(exc).__name__}") from exc
        return TokenClaims.from_payload(payload)


class SupabaseTokenVerifier:
    """Verifies Supabase access tokens against the project's JWKS.

    Keys are cached in memory and refreshed once when an unknown ``kid`` is
    seen, which is the standard behaviour during signing-key rotation.
    """

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        cache_seconds: int = 600,
        fetcher: JwksFetcher | None = None,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._cache_seconds = cache_seconds
        self._fetcher = fetcher or _default_jwks_fetcher
        self._keys: dict[str, dict[str, Any]] | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def _load_keys(self, *, force: bool = False) -> dict[str, dict[str, Any]]:
        async with self._lock:
            now = time.monotonic()
            if not force and self._keys is not None and now < self._expires_at:
                return self._keys

            try:
                document = await self._fetcher(self._jwks_url)
            except Exception as exc:  # network, HTTP status, invalid JSON
                logger.warning("auth.jwks_fetch_failed", error=str(exc))
                raise TokenError("signing keys are unavailable") from exc

            raw_keys = document.get("keys")
            if not isinstance(raw_keys, list):
                raise TokenError("JWKS document has no 'keys' array")

            keys: dict[str, dict[str, Any]] = {}
            for jwk in raw_keys:
                if not isinstance(jwk, Mapping):
                    continue
                kid = jwk.get("kid")
                kty = jwk.get("kty")
                use = jwk.get("use", "sig")
                if isinstance(kid, str) and isinstance(kty, str) and use == "sig":
                    keys[kid] = dict(jwk)

            if not keys:
                raise TokenError("JWKS document contains no usable signing keys")

            self._keys = keys
            self._expires_at = now + self._cache_seconds
            return keys

    async def _select_key(self, kid: str | None, *, refresh: bool) -> dict[str, Any]:
        keys = await self._load_keys(force=refresh)
        if kid is not None:
            jwk = keys.get(kid)
        elif len(keys) == 1:
            jwk = next(iter(keys.values()))
        else:
            jwk = None
        if jwk is None:
            raise TokenError("unknown signing key")
        return jwk

    async def verify(self, token: str) -> TokenClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenError("malformed token header") from exc

        algorithm = header.get("alg")
        if not isinstance(algorithm, str) or algorithm not in SUPABASE_ALLOWED_ALGORITHMS:
            raise TokenError("token uses an unsupported signing algorithm")

        kid = header.get("kid")
        kid = kid if isinstance(kid, str) else None

        try:
            jwk = await self._select_key(kid, refresh=False)
        except TokenError:
            # Possibly rotated: refresh the cache once before failing.
            jwk = await self._select_key(kid, refresh=True)

        try:
            public_key = jwt.PyJWK(jwk, algorithm=algorithm).key
        except jwt.PyJWTError as exc:
            raise TokenError("signing key could not be loaded") from exc

        try:
            payload = jwt.decode(
                token,
                public_key,
                algorithms=[algorithm],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise TokenError(f"supabase token rejected: {type(exc).__name__}") from exc

        return TokenClaims.from_payload(payload)


def build_verifier() -> TokenVerifier:
    """Construct the verifier for the configured auth mode."""
    if settings.auth_mode == "supabase":
        jwks_url = settings.jwks_url
        issuer = settings.jwt_issuer
        if not jwks_url or not issuer:  # pragma: no cover - guarded by Settings
            raise RuntimeError("Supabase auth mode requires SUPABASE_URL/JWKS configuration")
        return SupabaseTokenVerifier(
            jwks_url=jwks_url,
            issuer=issuer,
            audience=settings.supabase_jwt_audience,
            cache_seconds=settings.supabase_jwks_cache_seconds,
        )

    from app.auth.issuer import LOCAL_AUDIENCE

    return LocalTokenVerifier(
        secret=settings.local_jwt_secret,
        issuer=settings.local_jwt_issuer,
        audience=LOCAL_AUDIENCE,
    )


_verifier: TokenVerifier | None = None


def get_verifier() -> TokenVerifier:
    """Return the process-wide verifier (lazily built, replaceable in tests)."""
    global _verifier
    if _verifier is None:
        _verifier = build_verifier()
    return _verifier


def set_verifier(verifier: TokenVerifier | None) -> None:
    """Override the verifier (tests) or reset it to the configured default."""
    global _verifier
    _verifier = verifier


__all__ = [
    "LocalTokenVerifier",
    "SupabaseTokenVerifier",
    "TokenVerifier",
    "build_verifier",
    "get_verifier",
    "set_verifier",
]

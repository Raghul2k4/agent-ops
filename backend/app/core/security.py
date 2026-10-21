"""Password hashing, token generation, canonical hashing and cookie helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

SESSION_COOKIE_NAME = "agentops_session"
CSRF_COOKIE_NAME = "agentops_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"

_password_hasher = PasswordHasher(
    time_cost=settings.argon2_time_cost,
    memory_cost=settings.argon2_memory_cost,
    parallelism=settings.argon2_parallelism,
)


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Hash a plaintext password with argon2id."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against an argon2 hash, never raising."""
    try:
        _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def password_problems(password: str) -> list[str]:
    """Return a list of policy violations for a candidate password."""
    problems: list[str] = []
    if len(password) < 10:
        problems.append("must be at least 10 characters long")
    if len(password) > 256:
        problems.append("must be at most 256 characters long")
    if password.strip() != password:
        problems.append("must not start or end with whitespace")
    if not any(c.isalpha() for c in password):
        problems.append("must contain at least one letter")
    if not any(c.isdigit() for c in password):
        problems.append("must contain at least one digit")
    lowered = password.lower()
    for weak in ("password", "12345678", "qwerty", "letmein", "admin"):
        if weak in lowered:
            problems.append("must not contain a common weak sequence")
            break
    return problems


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
def generate_token(nbytes: int = 32) -> str:
    """Generate a URL-safe random token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Hash a bearer/session token for storage (plaintext is never persisted)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(candidate: str, stored_hash: str) -> bool:
    """Constant-time comparison of a presented token against a stored hash."""
    return hmac.compare_digest(hash_token(candidate), stored_hash)


def generate_api_key() -> tuple[str, str]:
    """Return ``(plaintext_key, prefix)`` for a new API key.

    The plaintext is shown to the operator exactly once; only its hash is stored.
    """
    prefix = "agoa"
    body = secrets.token_urlsafe(32)
    return f"{prefix}_{body}", prefix


# --------------------------------------------------------------------------- #
# Canonical payloads (used to bind approvals to an exact action)
# --------------------------------------------------------------------------- #
def canonical_json(payload: Any) -> str:
    """Serialise a payload to a deterministic JSON string.

    Keys are sorted, whitespace is removed and non-ASCII characters are
    preserved, so two semantically identical payloads always hash the same.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def hash_payload(payload: Any) -> str:
    """SHA-256 of the canonical JSON representation of a payload."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "SESSION_COOKIE_NAME",
    "canonical_json",
    "generate_api_key",
    "generate_token",
    "hash_password",
    "hash_payload",
    "hash_token",
    "password_problems",
    "tokens_match",
    "verify_password",
]

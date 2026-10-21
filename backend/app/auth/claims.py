"""Access-token claims shared by every verifier implementation."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class TokenError(Exception):
    """A token failed verification.

    The message is diagnostic only and must never be returned to a client: the
    API maps every verification failure onto a generic ``AUTHENTICATION_REQUIRED``
    response so token contents and failure reasons cannot be probed.
    """


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Verified identity claims, independent of the issuing provider."""

    subject: uuid.UUID
    audience: tuple[str, ...]
    expires_at: datetime
    issuer: str | None = None
    issued_at: datetime | None = None
    email: str | None = None
    role: str | None = None
    display_name: str | None = None
    raw: Mapping[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> TokenClaims:
        """Build claims from a decoded JWT payload.

        Raises ``TokenError`` when required claims are missing or malformed.
        """
        raw_subject = payload.get("sub")
        if not isinstance(raw_subject, str) or not raw_subject:
            raise TokenError("token is missing the 'sub' claim")
        try:
            subject = uuid.UUID(raw_subject)
        except ValueError as exc:
            raise TokenError("token subject is not a UUID") from exc

        raw_exp = payload.get("exp")
        if not isinstance(raw_exp, int | float):
            raise TokenError("token is missing the 'exp' claim")
        expires_at = datetime.fromtimestamp(raw_exp, tz=UTC)

        raw_aud = payload.get("aud")
        if isinstance(raw_aud, str):
            audience: tuple[str, ...] = (raw_aud,)
        elif isinstance(raw_aud, list) and all(isinstance(item, str) for item in raw_aud):
            audience = tuple(raw_aud)
        else:
            raise TokenError("token is missing the 'aud' claim")

        raw_iat = payload.get("iat")
        issued_at = (
            datetime.fromtimestamp(raw_iat, tz=UTC) if isinstance(raw_iat, int | float) else None
        )

        metadata = payload.get("user_metadata")
        display_name: str | None = None
        if isinstance(metadata, Mapping):
            for key in ("display_name", "full_name", "name"):
                candidate = metadata.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    display_name = candidate.strip()[:120]
                    break

        email = payload.get("email")
        issuer = payload.get("iss")
        role = payload.get("role")

        return cls(
            subject=subject,
            audience=audience,
            expires_at=expires_at,
            issuer=issuer if isinstance(issuer, str) else None,
            issued_at=issued_at,
            email=email if isinstance(email, str) else None,
            role=role if isinstance(role, str) else None,
            display_name=display_name,
            raw=dict(payload),
        )


__all__ = ["TokenClaims", "TokenError"]

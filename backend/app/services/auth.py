"""Identity services.

Two responsibilities:

* **Profile provisioning** - mirror a Supabase Auth identity into
  ``app.profiles`` on its first authenticated request. Authorization data is
  never read from token metadata; roles come from ``app.workspace_members``.
* **Development credentials** - register and authenticate local accounts for
  ``AUTH_MODE=local``. This path is disabled outside development/test.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from functools import lru_cache

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.claims import TokenClaims
from app.auth.issuer import issue_local_token, local_auth_available
from app.core.errors import (
    AuthenticationRequired,
    ConflictError,
    PermissionDenied,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.security import hash_password, password_problems, verify_password
from app.models.identity import LocalCredential, Profile

logger = get_logger(__name__)

_INVALID_CREDENTIALS = "Invalid email address or password."


def normalize_email(email: str) -> str:
    """Normalise an email address for storage and lookup."""
    return email.strip().lower()


@lru_cache(maxsize=1)
def _timing_equalizer_hash() -> str:
    """A real argon2 hash, verified against on unknown accounts.

    Computed lazily so importing the module stays fast, and cached so the cost
    is paid once rather than on every failed sign-in.
    """
    return hash_password("timing-equalizer-not-a-real-password")


def ensure_local_auth_enabled() -> None:
    """Reject development-only endpoints when Supabase owns identity."""
    if not local_auth_available():
        raise PermissionDenied(
            "Local sign-in is disabled. This deployment authenticates with Supabase Auth; "
            "sign in through the Supabase client to obtain an access token."
        )


async def register_local_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
) -> Profile:
    """Create a development account and its credential.

    Raises ``ValidationError`` for a weak password and ``ConflictError`` for a
    duplicate email.
    """
    ensure_local_auth_enabled()

    problems = password_problems(password)
    if problems:
        raise ValidationError(
            "The password does not meet the security policy.",
            details={"password_policy": problems},
        )

    normalized = normalize_email(email)
    existing = await session.scalar(
        select(Profile.id).where(func.lower(Profile.email) == normalized)
    )
    if existing is not None:
        raise ConflictError("An account with this email address already exists.")

    profile_id = uuid.uuid4()
    # `app.profiles.id` references `auth.users(id)`. Supabase Auth owns that
    # table in production; in development the migration shim provides it.
    await session.execute(
        text("insert into auth.users (id, email) values (:id, :email)"),
        {"id": profile_id, "email": normalized},
    )

    profile = Profile(
        id=profile_id,
        email=normalized,
        display_name=display_name.strip(),
        status="active",
    )
    session.add(profile)
    password_hash = hash_password(password)
    try:
        # `local_credentials` has no ORM relationship to `profiles`, so
        # SQLAlchemy cannot infer an insert order; flush the profile first or the
        # credential insert violates its foreign key.
        await session.flush()
        session.add(LocalCredential(profile_id=profile_id, password_hash=password_hash))
        await session.flush()
        await session.refresh(profile)
    except IntegrityError as exc:  # pragma: no cover - race condition guard
        await session.rollback()
        logger.warning("auth.registration_conflict", error=str(exc.orig))
        raise ConflictError("An account with this email address already exists.") from exc
    return profile


async def authenticate_local_user(session: AsyncSession, *, email: str, password: str) -> Profile:
    """Verify development credentials.

    Failures are indistinguishable between "unknown email" and "wrong password"
    to avoid account enumeration.
    """
    ensure_local_auth_enabled()

    normalized = normalize_email(email)
    row = (
        await session.execute(
            select(Profile, LocalCredential)
            .join(LocalCredential, LocalCredential.profile_id == Profile.id)
            .where(func.lower(Profile.email) == normalized)
        )
    ).first()

    if row is None:
        # Spend comparable time on unknown accounts to blunt timing attacks.
        verify_password(password, _timing_equalizer_hash())
        raise AuthenticationRequired(_INVALID_CREDENTIALS)

    profile, credential = row
    if not verify_password(password, credential.password_hash):
        raise AuthenticationRequired(_INVALID_CREDENTIALS)
    if profile.status != "active":
        raise AuthenticationRequired("This account is not active.")
    return profile


async def resolve_profile(session: AsyncSession, claims: TokenClaims) -> Profile:
    """Return the profile for a verified token, provisioning it on first sight.

    The identity key is always the token subject (``auth.users.id``); nothing
    else in the token is trusted for authorization.
    """
    profile = await session.get(Profile, claims.subject)
    if profile is not None:
        if profile.status != "active":
            raise AuthenticationRequired("This account is not active.")
        return profile

    if not claims.email:
        # M1 supports email identities. Phone-only Supabase identities have no
        # email claim, and inventing one would fabricate data.
        raise AuthenticationRequired(
            "This identity has no email address, which AgentOps requires for a profile."
        )

    profile = Profile(
        id=claims.subject,
        email=normalize_email(claims.email),
        display_name=(claims.display_name or claims.email.split("@")[0])[:120],
        status="active",
    )
    session.add(profile)
    try:
        await session.flush()
        await session.refresh(profile)
        await session.commit()
    except IntegrityError:
        # A concurrent first request won the race; adopt the stored profile. A
        # missing `auth.users` row (the identity was never created by Supabase
        # Auth) lands here too, so log the cause instead of guessing.
        await session.rollback()
        logger.warning("auth.profile_provisioning_failed", subject=str(claims.subject))
        profile = await session.get(Profile, claims.subject)
        if profile is None:  # pragma: no cover - defensive
            raise AuthenticationRequired("The identity could not be provisioned.") from None
        if profile.status != "active":
            raise AuthenticationRequired("This account is not active.") from None
        return profile

    logger.info("auth.profile_provisioned", profile_id=str(profile.id))
    return profile


def issue_access_token(profile: Profile) -> tuple[str, datetime]:
    """Issue a development access token for a profile."""
    return issue_local_token(subject=profile.id, email=profile.email)


__all__ = [
    "authenticate_local_user",
    "ensure_local_auth_enabled",
    "issue_access_token",
    "normalize_email",
    "register_local_user",
    "resolve_profile",
]

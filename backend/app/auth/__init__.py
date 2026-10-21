"""Authentication primitives: token claims, verification and local issuance."""

from app.auth.claims import TokenClaims, TokenError
from app.auth.issuer import issue_local_token, local_auth_available
from app.auth.verify import (
    SupabaseTokenVerifier,
    TokenVerifier,
    build_verifier,
    get_verifier,
    set_verifier,
)

__all__ = [
    "SupabaseTokenVerifier",
    "TokenClaims",
    "TokenError",
    "TokenVerifier",
    "build_verifier",
    "get_verifier",
    "issue_local_token",
    "local_auth_available",
    "set_verifier",
]

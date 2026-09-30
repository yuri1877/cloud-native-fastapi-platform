"""JWT verification (OIDC/OAuth2-compatible) and the authenticated principal.

Verification checks signature, issuer, audience and expiry (PyJWT enforces `exp` given
`require: ["exp"]`); nothing here implements password authentication.
"""

import logging
from collections.abc import Sequence
from typing import Any, Protocol

import jwt
from pydantic import BaseModel

from app.core.exceptions import AuthenticationException

logger = logging.getLogger(__name__)

REQUIRED_CLAIMS = ["exp", "iat", "sub"]


class SigningKey(Protocol):
    """Matches ``jwt.PyJWK``: only the ``.key`` attribute is used."""

    key: Any


class TokenVerifier(Protocol):
    """Matches ``jwt.PyJWKClient``'s public interface, so a real JWKS client and a
    lightweight test fake are interchangeable."""

    def get_signing_key_from_jwt(self, token: str) -> SigningKey: ...


class Principal(BaseModel):
    """The authenticated caller. Roles are used by Phase 10's authorization layer."""

    subject: str
    email: str | None = None
    roles: frozenset[str] = frozenset()


def create_token_verifier(jwks_url: str) -> TokenVerifier:
    """A ``PyJWKClient`` fetches and caches signing keys lazily; no network call happens here."""
    return jwt.PyJWKClient(jwks_url, cache_keys=True)


def decode_token(
    token: str,
    verifier: TokenVerifier,
    *,
    issuer: str,
    audience: str,
    algorithms: Sequence[str],
) -> dict[str, Any]:
    """Validate signature, issuer, audience and expiry. Never leaks internal detail:
    only the failure category is exposed to the caller; the exception type is logged."""
    try:
        signing_key = verifier.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=list(algorithms),
            issuer=issuer,
            audience=audience,
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationException("Token has expired", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthenticationException("Invalid token issuer", code="INVALID_ISSUER") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthenticationException("Invalid token audience", code="INVALID_AUDIENCE") from exc
    except jwt.PyJWTError as exc:
        # Malformed token, bad signature, unknown key ID, missing claims, etc. Collapsed into
        # one generic outcome so failure details are never exposed as an oracle to callers.
        logger.info("Token rejected: %s", type(exc).__name__)
        raise AuthenticationException("Invalid token", code="INVALID_TOKEN") from exc


def build_principal(claims: dict[str, Any]) -> Principal:
    roles = claims.get("roles") or []
    if not isinstance(roles, list):
        roles = []
    return Principal(
        subject=claims["sub"],
        email=claims.get("email"),
        roles=frozenset(str(r) for r in roles),
    )

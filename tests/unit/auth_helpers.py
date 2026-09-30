"""Shared helpers for auth tests: a local RSA keypair and a JWKS-client-shaped fake so
tests never hit the network. Not a test file itself (no test_ prefix)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://issuer.example.com/"
AUDIENCE = "platform-api"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


@dataclass
class FakeSigningKey:
    key: Any


class FakeTokenVerifier:
    """Duck-types ``jwt.PyJWKClient``: same method, always returns the test key pair,
    regardless of the token's ``kid`` (a real JWKS client picks the key by ``kid``)."""

    def get_signing_key_from_jwt(self, token: str) -> FakeSigningKey:  # noqa: ARG002
        return FakeSigningKey(key=_public_key)


def make_token(
    *,
    subject: str = "user-123",
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    expires_delta: timedelta = timedelta(minutes=5),
    roles: list[str] | None = None,
    extra_claims: dict[str, Any] | None = None,
    omit_claims: list[str] | None = None,
    headers: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + expires_delta,
    }
    if roles is not None:
        claims["roles"] = roles
    if extra_claims:
        claims.update(extra_claims)
    for field in omit_claims or []:
        claims.pop(field, None)
    return jwt.encode(claims, _private_key, algorithm="RS256", headers=headers)

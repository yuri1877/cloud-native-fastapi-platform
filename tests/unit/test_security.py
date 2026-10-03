from datetime import timedelta

import pytest

from app.core.exceptions import AuthenticationException
from app.core.security import Principal, build_principal, decode_token
from tests.unit.auth_helpers import AUDIENCE, ISSUER, FakeTokenVerifier, make_token


@pytest.fixture
def verifier() -> FakeTokenVerifier:
    return FakeTokenVerifier()


def test_valid_token_decodes(verifier: FakeTokenVerifier) -> None:
    token = make_token(subject="user-1", roles=["user", "operator"])
    claims = decode_token(token, verifier, issuer=ISSUER, audience=AUDIENCE, algorithms=["RS256"])
    assert claims["sub"] == "user-1"
    principal = build_principal(claims)
    assert principal == Principal(subject="user-1", roles=frozenset({"user", "operator"}))


def test_expired_token_rejected(verifier: FakeTokenVerifier) -> None:
    token = make_token(expires_delta=timedelta(minutes=-5))
    with pytest.raises(AuthenticationException) as excinfo:
        decode_token(token, verifier, issuer=ISSUER, audience=AUDIENCE, algorithms=["RS256"])
    assert excinfo.value.code == "TOKEN_EXPIRED"
    assert excinfo.value.status_code == 401


def test_wrong_issuer_rejected(verifier: FakeTokenVerifier) -> None:
    token = make_token(issuer="https://attacker.example.com/")
    with pytest.raises(AuthenticationException) as excinfo:
        decode_token(token, verifier, issuer=ISSUER, audience=AUDIENCE, algorithms=["RS256"])
    assert excinfo.value.code == "INVALID_ISSUER"


def test_wrong_audience_rejected(verifier: FakeTokenVerifier) -> None:
    token = make_token(audience="some-other-api")
    with pytest.raises(AuthenticationException) as excinfo:
        decode_token(token, verifier, issuer=ISSUER, audience=AUDIENCE, algorithms=["RS256"])
    assert excinfo.value.code == "INVALID_AUDIENCE"


def test_malformed_token_rejected(verifier: FakeTokenVerifier) -> None:
    with pytest.raises(AuthenticationException) as excinfo:
        decode_token("not-a-jwt", verifier, issuer=ISSUER, audience=AUDIENCE, algorithms=["RS256"])
    assert excinfo.value.code == "INVALID_TOKEN"


def test_missing_required_claim_rejected(verifier: FakeTokenVerifier) -> None:
    token = make_token(omit_claims=["sub"])
    with pytest.raises(AuthenticationException) as excinfo:
        decode_token(token, verifier, issuer=ISSUER, audience=AUDIENCE, algorithms=["RS256"])
    assert excinfo.value.code == "INVALID_TOKEN"


def test_error_message_never_leaks_library_exception_details(verifier: FakeTokenVerifier) -> None:
    token = make_token(expires_delta=timedelta(minutes=-5))
    with pytest.raises(AuthenticationException) as excinfo:
        decode_token(token, verifier, issuer=ISSUER, audience=AUDIENCE, algorithms=["RS256"])
    assert "jwt" not in excinfo.value.message.lower()
    assert "PyJWT" not in excinfo.value.message


def test_build_principal_defaults_roles_to_empty() -> None:
    principal = build_principal({"sub": "user-1"})
    assert principal.roles == frozenset()
    assert principal.email is None


def test_build_principal_ignores_non_list_roles_claim() -> None:
    principal = build_principal({"sub": "user-1", "roles": "not-a-list"})
    assert principal.roles == frozenset()

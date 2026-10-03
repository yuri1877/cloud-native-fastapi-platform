from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.exceptions import AppException, AuthenticationException
from app.core.security import Principal, TokenVerifier, build_principal, decode_token

# auto_error=False: a missing/malformed Authorization header is handled by our own
# exception (consistent error contract) rather than FastAPI's default 403.
_bearer_scheme = HTTPBearer(auto_error=False, description="OIDC/OAuth2 bearer JWT")


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        raise AppException(
            "Authentication is not configured", code="AUTH_NOT_CONFIGURED", status_code=503
        )
    return verifier


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if credentials is None:
        raise AuthenticationException()
    if settings.oidc_issuer is None or settings.oidc_audience is None:
        # Settings are validated together (app/core/config.py); this only happens if a
        # verifier was wired up in app.state without matching issuer/audience settings.
        raise AppException(
            "Authentication is not configured", code="AUTH_NOT_CONFIGURED", status_code=503
        )
    claims = decode_token(
        credentials.credentials,
        verifier,
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
        algorithms=settings.oidc_algorithms,
    )
    return build_principal(claims)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]

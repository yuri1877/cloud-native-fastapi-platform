"""Exposes the authenticated principal. Useful for clients to verify their token and roles."""

from fastapi import APIRouter

from app.dependencies.auth import CurrentPrincipal
from app.schemas.auth import PrincipalRead
from app.schemas.common import ErrorResponse

router = APIRouter(tags=["auth"])


@router.get(
    "/me",
    operation_id="get_current_principal",
    summary="Get the authenticated principal",
    response_model=PrincipalRead,
    responses={401: {"model": ErrorResponse, "description": "Missing or invalid token"}},
)
async def get_me(principal: CurrentPrincipal) -> PrincipalRead:
    return PrincipalRead(
        subject=principal.subject, email=principal.email, roles=sorted(principal.roles)
    )

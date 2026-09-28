"""Operational health endpoints (unversioned, for orchestrators and load balancers)."""

from fastapi import APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.exceptions import AppException
from app.db.database import check_database
from app.schemas.health import LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    operation_id="health_live",
    summary="Liveness probe",
    response_model=LivenessResponse,
)
async def live() -> LivenessResponse:
    """Process is alive. Deliberately has no external dependencies."""
    return LivenessResponse(status="ok")


@router.get(
    "/ready",
    operation_id="health_ready",
    summary="Readiness probe",
    response_model=ReadinessResponse,
    responses={503: {"description": "A critical dependency is unavailable"}},
)
async def ready(request: Request) -> ReadinessResponse:
    """Ready to serve traffic: the database (when configured) answers a trivial query."""
    engine: AsyncEngine | None = request.app.state.engine
    if engine is None:
        return ReadinessResponse(status="ready", checks={"database": "not_configured"})
    if not await check_database(engine):
        raise AppException("Service is not ready", code="NOT_READY", status_code=503)
    return ReadinessResponse(status="ready", checks={"database": "ok"})

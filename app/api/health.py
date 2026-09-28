"""Operational health endpoints (unversioned, for orchestrators and load balancers)."""

from fastapi import APIRouter

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
)
async def ready() -> ReadinessResponse:
    """Ready to serve traffic.

    No critical dependencies exist yet; the database check is added in Phase 4.
    """
    return ReadinessResponse(status="ready")

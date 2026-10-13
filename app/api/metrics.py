"""Prometheus scrape endpoint (unversioned, operational, like /health).

Unauthenticated by design - Prometheus scrapers do not carry user tokens - so it must only be
reachable from inside the cluster, never through the public ingress.
"""

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    return Response(content=request.app.state.metrics.render(), media_type=CONTENT_TYPE_LATEST)

"""Version 1 API router."""

from fastapi import APIRouter

from app.api.v1 import orders, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(users.router)
api_router.include_router(orders.router)

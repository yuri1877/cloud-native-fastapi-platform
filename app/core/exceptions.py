"""Centralised error contract.

Every error returned by the API has the shape::

    {"error": {"code": "...", "message": "...", "request_id": "..."}}

Internal exception details are logged but never returned to callers.
"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base class for expected application errors."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        super().__init__(self.message)


def _error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    # Real correlation IDs are attached in Phase 8; until then the field is null.
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
    )


async def _handle_app_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppException):  # defensive; handler is only registered for AppException
        return await _handle_unexpected(request, exc)
    return _error_response(request, exc.status_code, exc.code, exc.message)


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(request, 422, "VALIDATION_ERROR", "Request validation failed")


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    status_code = exc.status_code if isinstance(exc, StarletteHTTPException) else 500
    phrase = HTTPStatus(status_code).phrase
    return _error_response(request, status_code, phrase.upper().replace(" ", "_"), phrase)


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception", exc_info=(type(exc), exc, exc.__traceback__))
    return _error_response(request, 500, "INTERNAL_ERROR", "An internal error occurred")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, _handle_app_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)

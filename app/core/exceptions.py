"""Application exceptions and their HTTP representations."""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


logger = logging.getLogger(__name__)


class ApiError(Exception):
    """An expected application error that should become a JSON response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def error_content(status_code: int, message: str, data: Any = None) -> dict[str, Any]:
    return {"code": status_code, "msg": message, "data": data}


def register_exception_handlers(app: FastAPI) -> None:
    """Install handlers that keep every error response in the same format."""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content=error_content(exc.status_code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_content(
                status.HTTP_400_BAD_REQUEST,
                "invalid request parameters",
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        del request
        message = exc.detail if isinstance(exc.detail, str) else "request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_content(exc.status_code, message),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled error while serving %s %s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_content(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "internal server error",
            ),
        )

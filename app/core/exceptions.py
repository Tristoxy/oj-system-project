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

    # 函数 `__init__`：负责当前模块中的对应操作。
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# 函数 `error_content`：负责当前模块中的对应操作。
def error_content(status_code: int, message: str, data: Any = None) -> dict[str, Any]:
    return {"code": status_code, "msg": message, "data": data}


# 函数 `register_exception_handlers`：负责当前模块中的对应操作。
def register_exception_handlers(app: FastAPI) -> None:
    """Install handlers that keep every error response in the same format."""

    # 函数 `handle_api_error`：负责当前模块中的对应操作。
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content=error_content(exc.status_code, exc.message),
        )

    # 函数 `handle_validation_error`：负责当前模块中的对应操作。
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

    # 函数 `handle_http_error`：负责当前模块中的对应操作。
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

    # 函数 `handle_unexpected_error`：负责当前模块中的对应操作。
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

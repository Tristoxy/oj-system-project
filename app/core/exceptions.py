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

    # 保存业务错误对应的 HTTP 状态码和可返回给客户端的消息。
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message

# 生成错误json
# 按课程 API 约定生成统一的 code/msg/data 错误响应体。
def error_content(status_code: int, message: str, data: Any = None) -> dict[str, Any]:
    return {"code": status_code, "msg": message, "data": data}


# 为业务错误、参数错误、HTTP 错误和未知异常注册统一 JSON 处理器。
def register_exception_handlers(app: FastAPI) -> None:
    """Install handlers that keep every error response in the same format."""

    # 将代码主动抛出的 ApiError 原样转换为指定状态码的 JSON 响应。
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content=error_content(exc.status_code, exc.message),
        )

    # 把 FastAPI/Pydantic 默认的 422 参数错误改成课程要求的 400 格式。
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

    # 统一处理路由不存在等 Starlette HTTP 异常，同时保留原响应头。
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

    # 记录未预期异常的完整服务端堆栈，并只向客户端暴露通用 500 信息。
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

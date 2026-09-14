"""Service health endpoint."""

from fastapi import APIRouter

from app.core.responses import success_response


router = APIRouter(tags=["health"])

# 确认后端可以正常启动
# 提供无需登录的轻量探针，用来确认后端进程和路由可以响应。
@router.get("/health")
async def health_check() -> dict[str, object]:
    """Return a response proving that the API process is healthy."""
    return success_response({"status": "ok"})

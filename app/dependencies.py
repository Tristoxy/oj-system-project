"""Authentication and service-container dependencies."""

from fastapi import Request

from app.container import AppContainer
from app.core.config import SESSION_COOKIE
from app.core.exceptions import ApiError
from app.models.user import User


# 从 FastAPI 应用状态中取得启动时创建的服务容器。
def get_container(request: Request) -> AppContainer:
    return request.app.state.container


# 读取请求 Cookie 中的 Session ID，并解析为当前已登录用户。
async def get_current_user(request: Request) -> User:
    container = get_container(request)
    return await container.auth.current_user(request.cookies.get(SESSION_COOKIE))


# 在登录校验之上要求 admin 角色，否则以 403 拒绝请求。
async def require_admin(request: Request) -> User:
    user = await get_current_user(request)
    if user.role != "admin":
        raise ApiError(403, "administrator permission required")
    return user

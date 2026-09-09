"""Authentication and service-container dependencies."""

from fastapi import Request

from app.container import AppContainer
from app.core.config import SESSION_COOKIE
from app.core.exceptions import ApiError
from app.models.user import User


# 函数 `get_container`：负责当前模块中的对应操作。
def get_container(request: Request) -> AppContainer:
    return request.app.state.container


# 函数 `get_current_user`：负责当前模块中的对应操作。
async def get_current_user(request: Request) -> User:
    container = get_container(request)
    return await container.auth.current_user(request.cookies.get(SESSION_COOKIE))


# 函数 `require_admin`：负责当前模块中的对应操作。
async def require_admin(request: Request) -> User:
    user = await get_current_user(request)
    if user.role != "admin":
        raise ApiError(403, "administrator permission required")
    return user

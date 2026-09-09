"""Login and logout endpoints."""

from fastapi import APIRouter, Depends, Request, Response

from app.container import AppContainer
from app.core.config import SESSION_COOKIE, SESSION_TTL_SECONDS, secure_cookies
from app.core.responses import success_response
from app.dependencies import get_container, get_current_user
from app.models.user import Credentials, User


router = APIRouter(prefix="/api/auth", tags=["auth"])


# 函数 `login`：负责当前模块中的对应操作。
@router.post("/login")
async def login(
    payload: Credentials,
    response: Response,
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    user, session_id = await container.auth.login(payload)
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure_cookies(),
    )
    return success_response(
        {"user_id": user.user_id, "username": user.username, "role": user.role},
        msg="login success",
    )


# 函数 `logout`：负责当前模块中的对应操作。
@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del current_user
    await container.auth.logout(request.cookies.get(SESSION_COOKIE, ""))
    response.delete_cookie(SESSION_COOKIE)
    return success_response(None, msg="logout success")

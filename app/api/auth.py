"""Login and logout endpoints."""

from fastapi import APIRouter, Depends, Request, Response

from app.container import AppContainer
from app.core.config import SESSION_COOKIE, SESSION_TTL_SECONDS, secure_cookies
from app.core.responses import success_response
from app.dependencies import get_container, get_current_user
from app.models.user import Credentials, User


router = APIRouter(prefix="/api/auth", tags=["auth"])


# 校验账号密码，创建服务端 Session，并把 HttpOnly Session ID 写入 Cookie。
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


# 删除当前 Cookie 对应的服务端 Session，并要求浏览器清除该 Cookie。
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

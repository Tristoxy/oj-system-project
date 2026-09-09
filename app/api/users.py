"""User registration, lookup, listing, and role endpoints."""

from fastapi import APIRouter, Depends, Query

from app.container import AppContainer
from app.core.exceptions import ApiError
from app.core.responses import success_response
from app.dependencies import get_container, get_current_user, require_admin
from app.models.user import Credentials, RoleUpdate, User


router = APIRouter(prefix="/api/users", tags=["users"])


# 公开注册普通用户，密码由服务层哈希后保存。
@router.post("/")
async def register_user(
    payload: Credentials,
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    user = await container.users.create_user(payload)
    return success_response(user.public(), msg="register success")


# 仅现有管理员可创建新的管理员账号。
@router.post("/admin")
async def create_admin(
    payload: Credentials,
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    user = await container.users.create_user(payload, role="admin")
    return success_response({"user_id": user.user_id, "username": user.username})


# 仅管理员可分页查看去除密码字段后的用户列表及提交统计。
@router.get("/")
async def list_users(
    page: int | None = Query(default=None),
    page_size: int | None = Query(default=None),
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    return success_response(await container.users.list_users(page, page_size))


# 允许用户查看自己、管理员查看任意用户的公开资料。
@router.get("/{user_id}")
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    if current_user.role != "admin" and current_user.user_id != user_id:
        raise ApiError(403, "permission denied")
    user = await container.users.get_user(user_id)
    return success_response(user.public())


# 仅管理员可修改 user/admin/banned 角色，服务层保护最后一名管理员。
@router.put("/{user_id}/role")
async def update_role(
    user_id: str,
    payload: RoleUpdate,
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    user = await container.users.update_role(user_id, payload.role)
    return success_response({"user_id": user.user_id, "role": user.role}, msg="role updated")

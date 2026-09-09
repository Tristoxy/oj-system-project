"""User creation, lookup, roles, and statistics."""

from datetime import datetime, timezone

from app.core.exceptions import ApiError
from app.core.pagination import paginate
from app.core.security import hash_password
from app.models.user import Credentials, Role, User
from app.repositories.state_store import StateStore
from app.services.state_helpers import next_numeric_id, recompute_user_stats


class UserService:
    # 保存共享状态仓库，用户及角色变更通过原子修改写入。
    def __init__(self, store: StateStore) -> None:
        self.store = store

    # 检查用户名唯一性，生成递增用户 ID，并只持久化加盐密码哈希。
    async def create_user(self, credentials: Credentials, role: Role = "user") -> User:
        # 在状态锁内完成重名检查、用户模型构造和追加，防止并发重复注册。
        def create(state):
            if any(user["username"] == credentials.username for user in state["users"]):
                raise ApiError(400, "username already exists")
            user = User(
                user_id=next_numeric_id(state["users"], "user_id"),
                username=credentials.username,
                password=hash_password(credentials.password),
                role=role,
                join_time=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
            state["users"].append(user.model_dump(mode="json"))
            return user

        return await self.store.mutate(create)

    # 按用户 ID 查找并恢复为 User 模型，不存在时返回 404。
    async def get_user(self, user_id: str) -> User:
        state = await self.store.read()
        raw = next((user for user in state["users"] if user["user_id"] == user_id), None)
        if raw is None:
            raise ApiError(404, "user not found")
        return User.model_validate(raw)

    # 重新计算统计值、按数字 ID 排序并返回分页后的脱敏用户资料。
    async def list_users(self, page: int | None, page_size: int | None) -> dict[str, object]:
        state = await self.store.read()
        recompute_user_stats(state)
        users = [User.model_validate(item) for item in state["users"]]
        users.sort(
            key=lambda user: (
                (0, int(user.user_id))
                if user.user_id.isdigit()
                else (1, user.user_id)
            )
        )
        return {
            "total": len(users),
            "users": [user.public() for user in paginate(users, page, page_size)],
        }

    # 修改指定用户角色，但禁止降级或封禁系统中的最后一名管理员。
    async def update_role(self, user_id: str, role: Role) -> User:
        # 在状态锁内定位用户、检查最后管理员约束并保存新角色。
        def update(state):
            for raw in state["users"]:
                if raw["user_id"] == user_id:
                    if raw["role"] == "admin" and role != "admin":
                        admin_count = sum(
                            item["role"] == "admin" for item in state["users"]
                        )
                        if admin_count == 1:
                            raise ApiError(400, "cannot demote or ban the last administrator")
                    raw["role"] = role
                    return User.model_validate(raw)
            raise ApiError(404, "user not found")

        return await self.store.mutate(update)

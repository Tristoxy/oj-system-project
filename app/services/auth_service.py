"""Server-side cookie session management."""

import secrets
import time

from app.core.config import SESSION_TTL_SECONDS
from app.core.exceptions import ApiError
from app.core.security import verify_password
from app.models.user import Credentials, Session, User
from app.repositories.state_store import StateStore


class AuthService:
    # 保存共享状态仓库，所有登录态都持久化在 sessions 集合中。
    def __init__(self, store: StateStore) -> None:
        self.store = store

    # 根据用户名查找，验证密码哈希，检查是否封禁，生成随机sessionid及过期时间，返回用户、session
    # 校验凭据和封禁状态，清除过期会话后创建随机且有过期时间的新 Session。
    async def login(self, credentials: Credentials) -> tuple[User, str]:
        # 在一次原子状态修改中完成用户查找、密码验证、过期清理和会话写入。
        def create_session(state):
            raw = next(
                (user for user in state["users"] if user["username"] == credentials.username),
                None,
            )
            if raw is None or not verify_password(credentials.password, raw["password"]):
                raise ApiError(401, "invalid username or password")
            user = User.model_validate(raw)
            if user.role == "banned":
                raise ApiError(403, "user is banned")
            session = Session(
                session_id=secrets.token_urlsafe(32),
                user_id=user.user_id,
                expires_at=time.time() + SESSION_TTL_SECONDS,
            )
            state["sessions"] = [
                item for item in state["sessions"] if item["expires_at"] > time.time()
            ]
            state["sessions"].append(session.model_dump(mode="json"))
            return user, session.session_id

        return await self.store.mutate(create_session)

    # 删除指定 Session；不存在时按“未登录”处理而不是静默成功。
    async def logout(self, session_id: str) -> None:
        # 在状态锁内按 Session ID 过滤会话，并通过数量变化判断是否命中。
        def remove(state):
            before = len(state["sessions"])
            state["sessions"] = [
                session for session in state["sessions"] if session["session_id"] != session_id
            ]
            if len(state["sessions"]) == before:
                raise ApiError(401, "not logged in")

        await self.store.mutate(remove)

    # 依次校验 Session 存在、未过期、用户仍存在且未被封禁，再返回用户模型。
    async def current_user(self, session_id: str | None) -> User:
        if not session_id:
            raise ApiError(401, "not logged in")
        state = await self.store.read()
        session = next(
            (item for item in state["sessions"] if item["session_id"] == session_id),
            None,
        )
        if session is None or session["expires_at"] <= time.time():
            raise ApiError(401, "not logged in")
        raw = next(
            (user for user in state["users"] if user["user_id"] == session["user_id"]),
            None,
        )
        if raw is None:
            raise ApiError(401, "not logged in")
        user = User.model_validate(raw)
        if user.role == "banned":
            raise ApiError(403, "user is banned")
        return user

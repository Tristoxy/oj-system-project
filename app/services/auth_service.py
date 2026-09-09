"""Server-side cookie session management."""

import secrets
import time

from app.core.config import SESSION_TTL_SECONDS
from app.core.exceptions import ApiError
from app.core.security import verify_password
from app.models.user import Credentials, Session, User
from app.repositories.state_store import StateStore


class AuthService:
    # 函数 `__init__`：负责当前模块中的对应操作。
    def __init__(self, store: StateStore) -> None:
        self.store = store

    # 函数 `login`：负责当前模块中的对应操作。
    async def login(self, credentials: Credentials) -> tuple[User, str]:
        # 函数 `create_session`：负责当前模块中的对应操作。
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

    # 函数 `logout`：负责当前模块中的对应操作。
    async def logout(self, session_id: str) -> None:
        # 函数 `remove`：负责当前模块中的对应操作。
        def remove(state):
            before = len(state["sessions"])
            state["sessions"] = [
                session for session in state["sessions"] if session["session_id"] != session_id
            ]
            if len(state["sessions"]) == before:
                raise ApiError(401, "not logged in")

        await self.store.mutate(remove)

    # 函数 `current_user`：负责当前模块中的对应操作。
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

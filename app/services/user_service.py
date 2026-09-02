"""User creation, lookup, roles, and statistics."""

from datetime import datetime, timezone

from app.core.exceptions import ApiError
from app.core.pagination import paginate
from app.core.security import hash_password
from app.models.user import Credentials, Role, User
from app.repositories.state_store import StateStore
from app.services.state_helpers import next_numeric_id, recompute_user_stats


class UserService:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    async def create_user(self, credentials: Credentials, role: Role = "user") -> User:
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

    async def get_user(self, user_id: str) -> User:
        state = await self.store.read()
        raw = next((user for user in state["users"] if user["user_id"] == user_id), None)
        if raw is None:
            raise ApiError(404, "user not found")
        return User.model_validate(raw)

    async def list_users(self, page: int | None, page_size: int | None) -> dict[str, object]:
        state = await self.store.read()
        recompute_user_stats(state)
        users = [User.model_validate(item) for item in state["users"]]
        users.sort(key=lambda user: int(user.user_id) if user.user_id.isdigit() else user.user_id)
        return {
            "total": len(users),
            "users": [user.public() for user in paginate(users, page, page_size)],
        }

    async def update_role(self, user_id: str, role: Role) -> User:
        def update(state):
            for raw in state["users"]:
                if raw["user_id"] == user_id:
                    raw["role"] = role
                    return User.model_validate(raw)
            raise ApiError(404, "user not found")

        return await self.store.mutate(update)

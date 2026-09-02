"""Initialization, reset, export, and validated import."""

from datetime import datetime, timezone

from app.core.exceptions import ApiError
from app.core.security import hash_password
from app.models.language import Language
from app.models.problem import Problem
from app.models.submission import Submission
from app.models.system import ImportBundle
from app.models.user import User
from app.repositories.state_store import StateStore, empty_state
from app.services.state_helpers import recompute_user_stats


DEFAULT_LANGUAGES = [
    Language(
        name="python",
        file_ext=".py",
        run_cmd="python3 {src}",
        time_limit=3.0,
        memory_limit=128,
    ),
    Language(
        name="cpp",
        file_ext=".cpp",
        compile_cmd="g++ {src} -O2 -std=c++14 -o {exe}",
        run_cmd="{exe}",
        time_limit=3.0,
        memory_limit=128,
    ),
]


class SystemService:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    async def initialize(self) -> None:
        await self.store.initialize()

        def add_defaults(state):
            if not any(user.get("username") == "admin" for user in state["users"]):
                state["users"].append(self._initial_admin().model_dump(mode="json"))
            known = {language.get("name") for language in state["languages"]}
            for language in DEFAULT_LANGUAGES:
                if language.name not in known:
                    state["languages"].append(language.model_dump(mode="json"))

        await self.store.mutate(add_defaults)

    async def reset(self) -> None:
        await self.store.replace(empty_state())
        await self.store.clear_files()
        await self.initialize()

    async def export_data(self) -> dict[str, object]:
        state = await self.store.read()
        recompute_user_stats(state)
        users = [User.model_validate(item).model_dump(mode="json") for item in state["users"]]
        problems = [
            Problem.model_validate(item).model_dump(mode="json") for item in state["problems"]
        ]
        submissions = [
            Submission.model_validate(item).model_dump(mode="json", exclude={"pdg"})
            for item in state["submissions"]
        ]
        return {"users": users, "problems": problems, "submissions": submissions}

    async def import_data(self, bundle: ImportBundle) -> None:
        for user in bundle.users:
            if not user.password.startswith("pbkdf2_sha256$"):
                raise ApiError(400, "imported passwords must be hashed")

        def merge(state):
            self._merge(state["users"], [item.model_dump(mode="json") for item in bundle.users], "user_id")
            self._merge(state["problems"], [item.model_dump(mode="json") for item in bundle.problems], "id")
            self._merge(
                state["submissions"],
                [item.model_dump(mode="json") for item in bundle.submissions],
                "submission_id",
            )
            state["sessions"] = []
            recompute_user_stats(state)

        await self.store.mutate(merge)

    @staticmethod
    def _merge(target: list[dict], incoming: list[dict], key: str) -> None:
        indexes = {item[key]: index for index, item in enumerate(target)}
        for item in incoming:
            if item[key] in indexes:
                target[indexes[item[key]]] = item
            else:
                target.append(item)

    @staticmethod
    def _initial_admin() -> User:
        return User(
            user_id="1",
            username="admin",
            password=hash_password("admintestpassword"),
            role="admin",
            join_time=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )

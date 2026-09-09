"""Dynamic language registration."""

from app.core.exceptions import ApiError
from app.core.security import validate_command_template
from app.models.language import Language, LanguageCreate
from app.repositories.state_store import StateStore


class LanguageService:
    # 函数 `__init__`：负责当前模块中的对应操作。
    def __init__(self, store: StateStore) -> None:
        self.store = store

    # 函数 `list_languages`：负责当前模块中的对应操作。
    async def list_languages(self) -> list[str]:
        state = await self.store.read()
        return [item["name"] for item in state["languages"]]

    # 函数 `get_language`：负责当前模块中的对应操作。
    async def get_language(self, name: str) -> Language:
        state = await self.store.read()
        raw = next((item for item in state["languages"] if item["name"] == name), None)
        if raw is None:
            raise ApiError(404, "language not found")
        return Language.model_validate(raw)

    # 函数 `register`：负责当前模块中的对应操作。
    async def register(self, payload: LanguageCreate) -> Language:
        validate_command_template(payload.run_cmd)
        if "{src}" not in payload.run_cmd and "{exe}" not in payload.run_cmd:
            raise ApiError(400, "run command must contain {src} or {exe}")
        if payload.compile_cmd:
            validate_command_template(payload.compile_cmd, require_src=True)
        language = Language.model_validate(payload.model_dump())

        # 函数 `add`：负责当前模块中的对应操作。
        def add(state):
            if any(item["name"] == language.name for item in state["languages"]):
                raise ApiError(400, "language already exists")
            state["languages"].append(language.model_dump(mode="json"))
            return language

        return await self.store.mutate(add)

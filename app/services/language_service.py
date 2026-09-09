"""Dynamic language registration."""

from app.core.exceptions import ApiError
from app.core.security import validate_command_template
from app.models.language import Language, LanguageCreate
from app.repositories.state_store import StateStore


class LanguageService:
    # 保存共享状态仓库，动态语言配置会写入 languages 集合。
    def __init__(self, store: StateStore) -> None:
        self.store = store

    # 从持久化状态中按当前存储顺序提取所有语言名称。
    async def list_languages(self) -> list[str]:
        state = await self.store.read()
        return [item["name"] for item in state["languages"]]

    # 按名称读取并校验完整语言配置，不存在时返回 404。
    async def get_language(self, name: str) -> Language:
        state = await self.store.read()
        raw = next((item for item in state["languages"] if item["name"] == name), None)
        if raw is None:
            raise ApiError(404, "language not found")
        return Language.model_validate(raw)

    # 校验编译/运行命令的安全性和必要占位符，再持久化新语言。
    async def register(self, payload: LanguageCreate) -> Language:
        validate_command_template(payload.run_cmd)
        if "{src}" not in payload.run_cmd and "{exe}" not in payload.run_cmd:
            raise ApiError(400, "run command must contain {src} or {exe}")
        if payload.compile_cmd:
            validate_command_template(payload.compile_cmd, require_src=True)
        language = Language.model_validate(payload.model_dump())

        # 在状态锁内检查语言名唯一性，并追加已验证的完整配置。
        def add(state):
            if any(item["name"] == language.name for item in state["languages"]):
                raise ApiError(400, "language already exists")
            state["languages"].append(language.model_dump(mode="json"))
            return language

        return await self.store.mutate(add)

"""Runtime-only model configuration and AI problem-generation tasks."""

import asyncio
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.exceptions import ApiError
from app.models.ai import AIProblemTask, AIUsage, ModelConfigUpdate, ProblemTaskCreate
from app.models.problem import ProblemCreate
from app.models.user import User
from app.repositories.state_store import StateStore


@dataclass(frozen=True)
class _RuntimeModelConfig:
    provider_url: str
    model: str
    api_key: str
    input_price: float
    output_price: float
    price_unit: int

    # 函数 `public`：负责当前模块中的对应操作。
    def public(self) -> dict[str, object]:
        return {
            "provider_url": self.provider_url,
            "model": self.model,
            "api_key_configured": True,
            "input_price": self.input_price,
            "output_price": self.output_price,
            "price_unit": self.price_unit,
        }


class AIProblemService:
    """Run OpenAI-compatible requests without ever persisting model keys."""

    REQUEST_TIMEOUT_SECONDS = 90

    # 函数 `__init__`：负责当前模块中的对应操作。
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self._configs: dict[str, _RuntimeModelConfig] = {}
        self._records: dict[str, AIProblemTask] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    # 函数 `set_config`：负责当前模块中的对应操作。
    async def set_config(
        self, user: User, payload: ModelConfigUpdate
    ) -> dict[str, object]:
        config = _RuntimeModelConfig(**payload.model_dump())
        async with self._lock:
            self._configs[user.user_id] = config
        return config.public()

    # 函数 `get_config`：负责当前模块中的对应操作。
    async def get_config(self, user: User) -> dict[str, object]:
        async with self._lock:
            config = self._configs.get(user.user_id)
        if config is None:
            return {"api_key_configured": False}
        return config.public()

    # 函数 `create`：负责当前模块中的对应操作。
    async def create(self, payload: ProblemTaskCreate, user: User) -> AIProblemTask:
        async with self._lock:
            config = self._configs.get(user.user_id)
        if config is None:
            raise ApiError(400, "model configuration is required")

        reference: dict[str, Any] | None = None
        if payload.problem_id is not None:
            state = await self.store.read()
            reference = next(
                (
                    item
                    for item in state["problems"]
                    if item["id"] == payload.problem_id
                ),
                None,
            )
            if reference is None:
                raise ApiError(404, "problem not found")

        task_id = f"ai-{secrets.token_hex(8)}"
        record = AIProblemTask(task_id=task_id, user_id=user.user_id)
        async with self._lock:
            self._records[task_id] = record
            task = asyncio.create_task(
                self._generate(task_id, payload.requirement, reference, config)
            )
            self._tasks[task_id] = task
            task.add_done_callback(lambda done: self._remove_task(task_id, done))
        return record.model_copy(deep=True)

    # 函数 `get`：负责当前模块中的对应操作。
    async def get(self, task_id: str, user: User) -> AIProblemTask:
        async with self._lock:
            record = self._records.get(task_id)
            if record is None:
                raise ApiError(404, "AI problem task not found")
            if user.role != "admin" and record.user_id != user.user_id:
                raise ApiError(403, "permission denied")
            return record.model_copy(deep=True)

    # 函数 `cancel`：负责当前模块中的对应操作。
    async def cancel(self, task_id: str, user: User) -> AIProblemTask:
        async with self._lock:
            record = self._records.get(task_id)
            if record is None:
                raise ApiError(404, "AI problem task not found")
            if user.role != "admin" and record.user_id != user.user_id:
                raise ApiError(403, "permission denied")
            if record.status in {"success", "cancelled", "error"}:
                raise ApiError(409, "AI problem task has already finished")
            task = self._tasks.get(task_id)
            record.status = "cancelled"
            record.progress = "任务已中断"
            if task is not None:
                task.cancel()
            result = record.model_copy(deep=True)
        return result

    # 函数 `shutdown`：负责当前模块中的对应操作。
    async def shutdown(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        async with self._lock:
            # 重置、导入或进程关闭后，即使用户编号被复用，也不能继承他人的模型密钥。
            self._configs.clear()
            self._records.clear()

    # 函数 `_remove_task`：负责当前模块中的对应操作。
    def _remove_task(self, task_id: str, done: asyncio.Task[None]) -> None:
        if self._tasks.get(task_id) is done:
            self._tasks.pop(task_id, None)

    # 函数 `_set_progress`：负责当前模块中的对应操作。
    async def _set_progress(self, task_id: str, message: str) -> None:
        async with self._lock:
            record = self._records.get(task_id)
            if record is not None and record.status not in {"cancelled", "error"}:
                record.status = "running"
                record.progress = message

    # 函数 `_generate`：负责当前模块中的对应操作。
    async def _generate(
        self,
        task_id: str,
        requirement: str,
        reference: dict[str, Any] | None,
        config: _RuntimeModelConfig,
    ) -> None:
        try:
            await self._set_progress(task_id, "正在整理知识点和难度要求")
            messages = self._build_messages(requirement, reference)
            await self._set_progress(task_id, "正在调用模型生成题目与测试用例")
            response = await self._request_model(config, messages)
            await self._set_progress(task_id, "正在校验题目字段和测试用例")
            problem, usage = self._parse_response(response, config)
            async with self._lock:
                record = self._records[task_id]
                if record.status == "cancelled":
                    return
                record.status = "success"
                record.progress = "命题完成，可审阅并保存到题库"
                record.result = problem.model_dump(mode="json")
                record.usage = usage
                record.error = ""
        except asyncio.CancelledError:
            async with self._lock:
                record = self._records.get(task_id)
                if record is not None:
                    record.status = "cancelled"
                    record.progress = "任务已中断"
            raise
        except Exception:
            async with self._lock:
                record = self._records.get(task_id)
                if record is not None and record.status != "cancelled":
                    record.status = "error"
                    record.progress = "命题失败"
                    record.error = "模型请求或返回格式无效，请检查配置后重试"

    # 函数 `_build_messages`：负责当前模块中的对应操作。
    @staticmethod
    def _build_messages(
        requirement: str, reference: dict[str, Any] | None
    ) -> list[dict[str, str]]:
        schema = {
            "id": "unique_ascii_id",
            "title": "题目标题",
            "description": "完整题面",
            "input_description": "输入格式",
            "output_description": "输出格式",
            "samples": [{"input": "", "output": ""}],
            "constraints": "数据范围",
            "testcases": [{"input": "", "output": ""}],
            "hint": "提示",
            "source": "AI generated",
            "tags": ["知识点"],
            "time_limit": 1.0,
            "memory_limit": 128,
            "author": "AI assistant",
            "difficulty": "入门/简单/中等/困难",
        }
        system = (
            "你是程序设计课程命题助教。只返回一个 JSON 对象，不要 Markdown。"
            "题目必须可判定、输入输出无歧义，并提供至少 6 个覆盖普通、边界和较大规模情况的测试点。"
            "每个测试点的 output 必须正确。严格使用给定字段结构："
            + json.dumps(schema, ensure_ascii=False)
        )
        user = f"命题需求：{requirement}"
        if reference is not None:
            user += "\n需要参考或改写的现有题目：" + json.dumps(
                reference, ensure_ascii=False
            )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    # 函数 `_request_model`：负责当前模块中的对应操作。
    async def _request_model(
        self, config: _RuntimeModelConfig, messages: list[dict[str, str]]
    ) -> dict[str, Any]:
        endpoint = config.provider_url
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        body = {"model": config.model, "messages": messages, "temperature": 0.3}
        timeout = httpx.Timeout(self.REQUEST_TIMEOUT_SECONDS, connect=15)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("model response must be an object")
        return data

    # 函数 `_parse_response`：负责当前模块中的对应操作。
    @staticmethod
    def _parse_response(
        response: dict[str, Any], config: _RuntimeModelConfig
    ) -> tuple[ProblemCreate, AIUsage]:
        content = response["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("model content must be text")
        text = content.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        problem = ProblemCreate.model_validate(json.loads(text))

        raw_usage = response.get("usage") or {}
        input_tokens = int(raw_usage.get("prompt_tokens", raw_usage.get("input_tokens", 0)))
        output_tokens = int(
            raw_usage.get("completion_tokens", raw_usage.get("output_tokens", 0))
        )
        total_tokens = int(raw_usage.get("total_tokens", input_tokens + output_tokens))
        cost = (
            input_tokens / config.price_unit * config.input_price
            + output_tokens / config.price_unit * config.output_price
        )
        usage = AIUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=round(cost, 8),
        )
        return problem, usage

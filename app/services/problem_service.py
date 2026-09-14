"""Business rules for problem management and Special Judge files."""

import asyncio
import ast
from pathlib import Path

from pydantic import ValidationError

from app.core.exceptions import ApiError
from app.models.problem import Problem, ProblemCreate, ProblemUpdate
from app.repositories.state_store import StateStore


class ProblemService:
    # 保存状态仓库；题目元数据写入 JSON，SPJ 脚本单独保存在 spj 目录。
    def __init__(self, store: StateStore) -> None:
        self.store = store

    # 按题号排序并只返回检索列表需要的 id 与 title，避免泄露隐藏测例。
    async def list_problems(self) -> list[dict[str, str]]:
        state = await self.store.read()
        problems = sorted(state["problems"], key=lambda item: item["id"])
        return [{"id": item["id"], "title": item["title"]} for item in problems]

    # 按题目id获取完整题目配置并通过 Pydantic 恢复类型。
    async def get_problem(self, problem_id: str) -> Problem:
        state = await self.store.read()
        raw = next((item for item in state["problems"] if item["id"] == problem_id), None)
        if raw is None:
            raise ApiError(404, "problem not found")
        return Problem.model_validate(raw)

    # 新增题目，将已校验的创建请求转换为存储模型，并保证题号全局唯一。
    async def add_problem(self, payload: ProblemCreate) -> Problem:
        problem = Problem.model_validate(payload.model_dump())

        # 在状态锁内再次检查题号冲突并追加题目，避免并发创建重号。
        def add(state):
            if any(item["id"] == problem.id for item in state["problems"]):
                raise ApiError(409, "problem id already exists")
            state["problems"].append(problem.model_dump(mode="json"))
            return problem

        return await self.store.mutate(add)

    # 从状态中删除题目；成功后再清理同题号的可选 SPJ 文件。
    async def delete_problem(self, problem_id: str) -> None:
        # 在状态锁内查找并移除题目，不存在时返回 404。
        def delete(state):
            for index, item in enumerate(state["problems"]):
                if item["id"] == problem_id:
                    state["problems"].pop(index)
                    return
            raise ApiError(404, "problem not found")

        await self.store.mutate(delete)
        spj_file = self.spj_path(problem_id)
        if spj_file.exists():
            spj_file.unlink()

    # 修改题目，合并请求中实际提供的字段，拒绝改题号并重新校验完整题目。
    async def update_problem(self, problem_id: str, payload: ProblemUpdate) -> Problem:
        changes = payload.model_dump(exclude_unset=True)
        requested_id = changes.pop("id", None)
        if requested_id is not None and requested_id != problem_id:
            raise ApiError(400, "problem id cannot be changed")

        # 在状态锁内定位旧题目、合并字段并以验证后的模型整体替换。
        def update(state):
            for index, raw in enumerate(state["problems"]):
                if raw["id"] != problem_id:
                    continue
                merged = {**raw, **changes}
                try:
                    problem = Problem.model_validate(merged)
                except ValidationError as exc:
                    raise ApiError(400, "invalid problem update") from exc
                state["problems"][index] = problem.model_dump(mode="json")
                return problem
            raise ApiError(404, "problem not found")

        return await self.store.mutate(update)

    # 独立修改题目的 public_cases 开关，控制评测测例详情是否公开。
    async def set_log_visibility(self, problem_id: str, public_cases: bool) -> Problem:
        # 在状态锁内定位题目并保存新的测例可见性。
        def update(state):
            for item in state["problems"]:
                if item["id"] == problem_id:
                    item["public_cases"] = public_cases
                    return Problem.model_validate(item)
            raise ApiError(404, "problem not found")

        return await self.store.mutate(update)

    # 把经过题号正则校验的 ID 映射为数据目录中的SPJ文件的固定 Python 文件路径。
    def spj_path(self, problem_id: str) -> Path:
        return self.store.spj_dir / f"{problem_id}.py"

    # 校验题目、文件类型/大小、Python 语法及危险 AST 操作后原子保存 SPJ。
    async def save_spj(self, problem_id: str, filename: str, content: bytes) -> None:
        problem = await self.get_problem(problem_id)
        if not filename.endswith(".py"):
            raise ApiError(400, "SPJ script must be a Python file")
        if len(content) > 256_000:
            raise ApiError(400, "SPJ script is too large")
        try:
            text = content.decode("utf-8")
            tree = ast.parse(text)
        except (UnicodeDecodeError, SyntaxError) as exc:
            raise ApiError(400, "invalid SPJ script") from exc
        allowed_imports = {
            "collections",
            "decimal",
            "fractions",
            "functools",
            "itertools",
            "math",
            "re",
            "statistics",
            "sys",
        }
        forbidden_calls = {
            "__import__",
            "compile",
            "delattr",
            "eval",
            "exec",
            "getattr",
            "globals",
            "locals",
            "setattr",
            "vars",
        }
        forbidden_attributes = {
            "chmod",
            "chown",
            "kill",
            "popen",
            "remove",
            "rename",
            "replace",
            "rmdir",
            "system",
            "unlink",
            "write_bytes",
            "write_text",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name.split(".")[0] not in allowed_imports for alias in node.names
            ):
                raise ApiError(400, "unsafe SPJ import")
            if isinstance(node, ast.ImportFrom) and (
                node.module or ""
            ).split(".")[0] not in allowed_imports:
                raise ApiError(400, "unsafe SPJ import")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in forbidden_calls
            ):
                raise ApiError(400, "unsafe SPJ operation")
            if isinstance(node, ast.Attribute) and (
                node.attr.startswith("__") or node.attr in forbidden_attributes
            ):
                raise ApiError(400, "unsafe SPJ operation")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "open"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                raise ApiError(400, "SPJ may only open paths passed by the judge")

        await asyncio.to_thread(self._write_spj, problem_id, text)
        if problem.judge_mode != "spj":
            await self._set_judge_mode(problem_id, "spj")

    # 删除存在的 SPJ 脚本，并把题目评测模式恢复为 standard。
    async def delete_spj(self, problem_id: str) -> None:
        await self.get_problem(problem_id)
        path = self.spj_path(problem_id)
        if not path.exists():
            raise ApiError(404, "SPJ script not found")
        await asyncio.to_thread(path.unlink)
        await self._set_judge_mode(problem_id, "standard")

    # 通过同目录临时文件写入并 replace，防止 SPJ 文件只写入一部分。
    def _write_spj(self, problem_id: str, text: str) -> None:
        self.store.spj_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.spj_path(problem_id).with_suffix(".py.tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(self.spj_path(problem_id))

    # 在持久化题目上切换 standard 或 spj 模式，与脚本文件状态保持一致。
    async def _set_judge_mode(self, problem_id: str, mode: str) -> None:
        # 在状态锁内按题号更新 judge_mode，不存在则返回 404。
        def update(state):
            for item in state["problems"]:
                if item["id"] == problem_id:
                    item["judge_mode"] = mode
                    return
            raise ApiError(404, "problem not found")

        await self.store.mutate(update)

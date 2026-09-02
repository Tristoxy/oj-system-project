"""Business rules for problem management and Special Judge files."""

import asyncio
import ast
from pathlib import Path

from app.core.exceptions import ApiError
from app.models.problem import Problem, ProblemCreate
from app.repositories.state_store import StateStore


class ProblemService:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    async def list_problems(self) -> list[dict[str, str]]:
        state = await self.store.read()
        problems = sorted(state["problems"], key=lambda item: item["id"])
        return [{"id": item["id"], "title": item["title"]} for item in problems]

    async def get_problem(self, problem_id: str) -> Problem:
        state = await self.store.read()
        raw = next((item for item in state["problems"] if item["id"] == problem_id), None)
        if raw is None:
            raise ApiError(404, "problem not found")
        return Problem.model_validate(raw)

    async def add_problem(self, payload: ProblemCreate) -> Problem:
        problem = Problem.model_validate(payload.model_dump())

        def add(state):
            if any(item["id"] == problem.id for item in state["problems"]):
                raise ApiError(409, "problem id already exists")
            state["problems"].append(problem.model_dump(mode="json"))
            return problem

        return await self.store.mutate(add)

    async def delete_problem(self, problem_id: str) -> None:
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

    async def set_log_visibility(self, problem_id: str, public_cases: bool) -> Problem:
        def update(state):
            for item in state["problems"]:
                if item["id"] == problem_id:
                    item["public_cases"] = public_cases
                    return Problem.model_validate(item)
            raise ApiError(404, "problem not found")

        return await self.store.mutate(update)

    def spj_path(self, problem_id: str) -> Path:
        return self.store.spj_dir / f"{problem_id}.py"

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

    async def delete_spj(self, problem_id: str) -> None:
        await self.get_problem(problem_id)
        path = self.spj_path(problem_id)
        if not path.exists():
            raise ApiError(404, "SPJ script not found")
        await asyncio.to_thread(path.unlink)
        await self._set_judge_mode(problem_id, "standard")

    def _write_spj(self, problem_id: str, text: str) -> None:
        self.store.spj_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.spj_path(problem_id).with_suffix(".py.tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(self.spj_path(problem_id))

    async def _set_judge_mode(self, problem_id: str, mode: str) -> None:
        def update(state):
            for item in state["problems"]:
                if item["id"] == problem_id:
                    item["judge_mode"] = mode
                    return
            raise ApiError(404, "problem not found")

        await self.store.mutate(update)

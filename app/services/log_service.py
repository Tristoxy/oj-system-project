"""Evaluation-log visibility and access auditing."""

from datetime import datetime, timezone

from app.core.exceptions import ApiError
from app.core.pagination import paginate
from app.models.log import AccessLog
from app.models.problem import Problem
from app.models.submission import Submission
from app.models.user import User
from app.repositories.state_store import StateStore


class LogService:
    # 函数 `__init__`：负责当前模块中的对应操作。
    def __init__(self, store: StateStore) -> None:
        self.store = store

    # 函数 `get_log`：负责当前模块中的对应操作。
    async def get_log(self, submission_id: str, user: User) -> dict[str, object]:
        state = await self.store.read()
        raw_submission = next(
            (item for item in state["submissions"] if item["submission_id"] == submission_id),
            None,
        )
        if raw_submission is None:
            raise ApiError(404, "submission not found")
        submission = Submission.model_validate(raw_submission)
        raw_problem = next(
            (item for item in state["problems"] if item["id"] == submission.problem_id),
            None,
        )
        if raw_problem is None:
            raise ApiError(404, "problem not found")
        problem = Problem.model_validate(raw_problem)
        allowed = user.role == "admin" or submission.user_id == user.user_id or problem.public_cases
        await self._record(user.user_id, problem.id, 200 if allowed else 403)
        if not allowed:
            raise ApiError(403, "permission denied")
        data: dict[str, object] = {"score": submission.score, "counts": submission.counts}
        if user.role == "admin" or problem.public_cases:
            data["details"] = [detail.model_dump(mode="json") for detail in submission.details]
        return data

    # 函数 `list_access_logs`：负责当前模块中的对应操作。
    async def list_access_logs(
        self,
        user_id: str | None,
        problem_id: str | None,
        page: int | None,
        page_size: int | None,
    ) -> list[dict[str, object]]:
        state = await self.store.read()
        items = [AccessLog.model_validate(item) for item in state["access_logs"]]
        if user_id is not None:
            items = [item for item in items if item.user_id == user_id]
        if problem_id is not None:
            items = [item for item in items if item.problem_id == problem_id]
        items.sort(key=lambda item: item.time, reverse=True)
        return [item.model_dump(mode="json") for item in paginate(items, page, page_size)]

    # 函数 `_record`：负责当前模块中的对应操作。
    async def _record(self, user_id: str, problem_id: str, status_code: int) -> None:
        log = AccessLog(
            user_id=user_id,
            problem_id=problem_id,
            time=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            status=str(status_code),
        )
        await self.store.mutate(
            lambda state: state["access_logs"].append(log.model_dump(mode="json"))
        )

"""Submission lifecycle, filtering, rejudging, and background evaluation."""

import asyncio
from datetime import datetime, timedelta, timezone

from app.core.config import SUBMISSION_RATE_LIMIT, SUBMISSION_RATE_WINDOW_SECONDS
from app.core.exceptions import ApiError
from app.core.pagination import paginate
from app.judge.runner import JudgeRunner
from app.models.language import Language
from app.models.problem import Problem
from app.models.submission import Submission, SubmissionCreate
from app.models.user import User
from app.plagiarism.pdg import build_pdg
from app.repositories.state_store import StateStore
from app.services.state_helpers import next_numeric_id, recompute_user_stats


class SubmissionService:
    def __init__(self, store: StateStore, runner: JudgeRunner) -> None:
        self.store = store
        self.runner = runner
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def submit(self, payload: SubmissionCreate, user: User) -> Submission:
        now = datetime.now(timezone.utc)

        def create(state):
            cutoff = now - timedelta(seconds=SUBMISSION_RATE_WINDOW_SECONDS)
            recent = 0
            for item in state["submissions"]:
                if item["user_id"] != user.user_id:
                    continue
                try:
                    if datetime.fromisoformat(item["created_at"]) >= cutoff:
                        recent += 1
                except (KeyError, ValueError):
                    pass
            if recent >= SUBMISSION_RATE_LIMIT:
                raise ApiError(429, "submission rate limit exceeded")
            problem = next(
                (item for item in state["problems"] if item["id"] == payload.problem_id),
                None,
            )
            language = next(
                (item for item in state["languages"] if item["name"] == payload.language),
                None,
            )
            if problem is None:
                raise ApiError(404, "problem not found")
            if language is None:
                raise ApiError(404, "language not found")
            submission = Submission(
                submission_id=next_numeric_id(state["submissions"], "submission_id"),
                user_id=user.user_id,
                problem_id=payload.problem_id,
                language=payload.language,
                code=payload.code,
                counts=len(problem.get("testcases", [])) * 10,
                created_at=now.isoformat(),
                pdg=build_pdg(payload.code, payload.language),
            )
            state["submissions"].append(submission.model_dump(mode="json"))
            recompute_user_stats(state)
            return submission

        submission = await self.store.mutate(create)
        await self._schedule(submission.submission_id)
        return submission

    async def get_submission(self, submission_id: str) -> Submission:
        state = await self.store.read()
        raw = next(
            (item for item in state["submissions"] if item["submission_id"] == submission_id),
            None,
        )
        if raw is None:
            raise ApiError(404, "submission not found")
        return Submission.model_validate(raw)

    async def result_for(self, submission_id: str, user: User) -> dict[str, object]:
        submission = await self.get_submission(submission_id)
        if user.role != "admin" and submission.user_id != user.user_id:
            raise ApiError(403, "permission denied")
        if submission.status != "success":
            return {"submission_id": submission.submission_id, "status": submission.status}
        return {"score": submission.score, "counts": submission.counts}

    async def list_submissions(
        self,
        user: User,
        user_id: str | None,
        problem_id: str | None,
        submission_status: str | None,
        page: int | None,
        page_size: int | None,
    ) -> dict[str, object]:
        if user_id is None and problem_id is None:
            raise ApiError(400, "user_id or problem_id is required")
        if user.role != "admin" and user_id not in {None, user.user_id}:
            raise ApiError(403, "permission denied")
        if submission_status not in {None, "pending", "success", "error"}:
            raise ApiError(400, "invalid submission status")
        effective_user = user_id if user.role == "admin" else user.user_id
        state = await self.store.read()
        items = [Submission.model_validate(item) for item in state["submissions"]]
        if effective_user is not None:
            items = [item for item in items if item.user_id == effective_user]
        if problem_id is not None:
            items = [item for item in items if item.problem_id == problem_id]
        if submission_status is not None:
            items = [item for item in items if item.status == submission_status]
        items.sort(key=lambda item: item.created_at, reverse=True)
        total = len(items)
        selected = paginate(items, page, page_size)
        result = []
        for item in selected:
            summary: dict[str, object] = {
                "submission_id": item.submission_id,
                "status": item.status,
            }
            if item.status == "success":
                summary.update(score=item.score, counts=item.counts)
            result.append(summary)
        return {"total": total, "submissions": result}

    async def rejudge(self, submission_id: str) -> Submission:
        def reset(state):
            for item in state["submissions"]:
                if item["submission_id"] == submission_id:
                    item.update(status="pending", details=[], score=0)
                    return Submission.model_validate(item)
            raise ApiError(404, "submission not found")

        submission = await self.store.mutate(reset)
        await self._schedule(submission_id)
        return submission

    async def resume_pending(self) -> None:
        state = await self.store.read()
        for item in state["submissions"]:
            if item.get("status") == "pending":
                await self._schedule(str(item["submission_id"]))

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def wait(self, submission_id: str, timeout: float = 10) -> Submission:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            submission = await self.get_submission(submission_id)
            if submission.status != "pending":
                return submission
            await asyncio.sleep(0.02)
        raise TimeoutError(f"submission {submission_id} did not finish")

    async def _schedule(self, submission_id: str) -> None:
        previous = self._tasks.get(submission_id)
        if previous is not None and not previous.done():
            previous.cancel()
            await asyncio.gather(previous, return_exceptions=True)
        task = asyncio.create_task(self._evaluate(submission_id))
        self._tasks[submission_id] = task

        def remove(done: asyncio.Task[None]) -> None:
            if self._tasks.get(submission_id) is done:
                self._tasks.pop(submission_id, None)

        task.add_done_callback(remove)

    async def _evaluate(self, submission_id: str) -> None:
        try:
            state = await self.store.read()
            raw_submission = next(
                item for item in state["submissions"] if item["submission_id"] == submission_id
            )
            raw_problem = next(
                item for item in state["problems"] if item["id"] == raw_submission["problem_id"]
            )
            raw_language = next(
                item for item in state["languages"] if item["name"] == raw_submission["language"]
            )
            submission = Submission.model_validate(raw_submission)
            problem = Problem.model_validate(raw_problem)
            language = Language.model_validate(raw_language)
            details = await self.runner.judge(submission.code, language, problem)
            score = sum(10 for detail in details if detail.result == "AC")
            pdg = submission.pdg or build_pdg(submission.code, submission.language)

            def finish(current):
                for item in current["submissions"]:
                    if item["submission_id"] == submission_id:
                        item.update(
                            status="success",
                            details=[detail.model_dump(mode="json") for detail in details],
                            score=score,
                            counts=len(problem.testcases) * 10,
                            pdg=pdg,
                        )
                        break
                recompute_user_stats(current)

            await self.store.mutate(finish)
        except Exception:
            def fail(state):
                for item in state["submissions"]:
                    if item["submission_id"] == submission_id:
                        item["status"] = "error"
                        break
                recompute_user_stats(state)

            await self.store.mutate(fail)

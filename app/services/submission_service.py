"""Submission lifecycle, filtering, rejudging, and background evaluation."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.core.config import SUBMISSION_RATE_LIMIT, SUBMISSION_RATE_WINDOW_SECONDS
from app.core.exceptions import ApiError
from app.core.pagination import paginate
from app.judge.runner import JudgeRunner
from app.models.language import Language
from app.models.problem import Problem
from app.models.submission import JudgeSnapshot, Submission, SubmissionCreate
from app.models.user import User
from app.plagiarism.pdg import build_pdg
from app.repositories.state_store import StateStore
from app.services.state_helpers import next_numeric_id, recompute_user_stats


logger = logging.getLogger(__name__)


class SubmissionService:
    # 保存状态仓库和评测器，并按 submission_id 追踪运行中的后台评测任务。
    def __init__(self, store: StateStore, runner: JudgeRunner) -> None:
        self.store = store
        self.runner = runner
        self._tasks: dict[str, asyncio.Task[None]] = {}

    # 执行一分钟限流和外键校验，保存题目/语言快照后创建异步评测。
    async def submit(self, payload: SubmissionCreate, user: User) -> Submission:
        now = datetime.now(timezone.utc)

        # 在状态锁内完成限流统计、题目语言查找、编号分配和 pending 记录写入。
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
                judge_snapshot=JudgeSnapshot(
                    problem=Problem.model_validate(problem),
                    language=Language.model_validate(language),
                ),
            )
            state["submissions"].append(submission.model_dump(mode="json"))
            recompute_user_stats(state)
            return submission

        submission = await self.store.mutate(create)
        await self._schedule(submission.submission_id)
        return submission

    # 按提交编号读取完整内部记录并恢复为 Submission 模型。
    async def get_submission(self, submission_id: str) -> Submission:
        state = await self.store.read()
        raw = next(
            (item for item in state["submissions"] if item["submission_id"] == submission_id),
            None,
        )
        if raw is None:
            raise ApiError(404, "submission not found")
        return Submission.model_validate(raw)

    # 校验本人或管理员权限，pending 时返回基础状态，结束后附加编译运行信息。
    async def result_for(self, submission_id: str, user: User) -> dict[str, object]:
        submission = await self.get_submission(submission_id)
        if user.role != "admin" and submission.user_id != user.user_id:
            raise ApiError(403, "permission denied")
        data: dict[str, object] = {
            "submission_id": submission.submission_id,
            "user_id": submission.user_id,
            "problem_id": submission.problem_id,
            "language": submission.language,
            "created_at": submission.created_at,
            "status": submission.status,
        }
        if submission.status == "pending":
            return data
        data.update(
            score=submission.score,
            counts=submission.counts,
            compile_info=submission.compile_info,
            run_info=submission.run_info,
            error_info=submission.error_info,
        )
        return data

    # 校验筛选条件和用户权限，分页返回带最终 verdict 的提交摘要。
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
                "user_id": item.user_id,
                "problem_id": item.problem_id,
                "language": item.language,
                "created_at": item.created_at,
                "status": item.status,
            }
            if item.status == "success":
                verdict = "AC"
                for detail in item.details:
                    if detail.result != "AC":
                        verdict = detail.result
                        break
                summary.update(score=item.score, counts=item.counts, verdict=verdict)
            elif item.status == "error":
                summary["verdict"] = "SYSTEM_ERROR"
            else:
                summary["verdict"] = "PENDING"
            result.append(summary)
        return {"total": total, "submissions": result}

    # 读取当前题目和语言重新生成快照、清空旧结果，并再次调度该提交。
    async def rejudge(self, submission_id: str) -> Submission:
        # 在状态锁内将指定提交恢复为 pending，同时重置分数、详情和运行信息。
        def reset(state):
            for item in state["submissions"]:
                if item["submission_id"] == submission_id:
                    problem = next(
                        (
                            problem
                            for problem in state["problems"]
                            if problem["id"] == item["problem_id"]
                        ),
                        None,
                    )
                    language = next(
                        (
                            language
                            for language in state["languages"]
                            if language["name"] == item["language"]
                        ),
                        None,
                    )
                    if problem is None:
                        raise ApiError(404, "problem not found")
                    if language is None:
                        raise ApiError(404, "language not found")
                    item.update(
                        status="pending",
                        details=[],
                        score=0,
                        counts=len(problem.get("testcases", [])) * 10,
                        compile_info=None,
                        run_info=None,
                        error_info="",
                        judge_snapshot=JudgeSnapshot(
                            problem=Problem.model_validate(problem),
                            language=Language.model_validate(language),
                        ).model_dump(mode="json"),
                    )
                    recompute_user_stats(state)
                    return Submission.model_validate(item)
            raise ApiError(404, "submission not found")

        submission = await self.store.mutate(reset)
        await self._schedule(submission_id)
        return submission

    # 应用启动或导入结束后，把持久化的 pending 提交逐个重新加入评测队列。
    async def resume_pending(self) -> None:
        state = await self.store.read()
        for item in state["submissions"]:
            if item.get("status") == "pending":
                await self._schedule(str(item["submission_id"]))

    # 取消并等待所有评测 Task，确保重置、导入和关闭期间不再回写旧状态。
    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # 供测试轮询单次提交，直到不再 pending 或达到指定超时时间。
    async def wait(self, submission_id: str, timeout: float = 10) -> Submission:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            submission = await self.get_submission(submission_id)
            if submission.status != "pending":
                return submission
            await asyncio.sleep(0.02)
        raise TimeoutError(f"submission {submission_id} did not finish")

    # 每个提交只保留一个评测 Task；重复调度时先取消并等待旧 Task。
    async def _schedule(self, submission_id: str) -> None:
        previous = self._tasks.get(submission_id)
        if previous is not None and not previous.done():
            previous.cancel()
            await asyncio.gather(previous, return_exceptions=True)
        task = asyncio.create_task(self._evaluate(submission_id))
        self._tasks[submission_id] = task

        # Task 完成回调只清除仍指向自身的映射，避免与重新评测产生竞态。
        def remove(done: asyncio.Task[None]) -> None:
            if self._tasks.get(submission_id) is done:
                self._tasks.pop(submission_id, None)

        task.add_done_callback(remove)

    # 使用提交快照执行全部测例、计算分数和 PDG，再原子写入成功或错误终态。
    async def _evaluate(self, submission_id: str) -> None:
        try:
            state = await self.store.read()
            raw_submission = next(
                item for item in state["submissions"] if item["submission_id"] == submission_id
            )
            submission = Submission.model_validate(raw_submission)
            if submission.judge_snapshot is not None:
                problem = submission.judge_snapshot.problem
                language = submission.judge_snapshot.language
            else:
                raw_problem = next(
                    item
                    for item in state["problems"]
                    if item["id"] == raw_submission["problem_id"]
                )
                raw_language = next(
                    item
                    for item in state["languages"]
                    if item["name"] == raw_submission["language"]
                )
                problem = Problem.model_validate(raw_problem)
                language = Language.model_validate(raw_language)
            details = await self.runner.judge(submission.code, language, problem)
            score = sum(10 for detail in details if detail.result == "AC")
            pdg = submission.pdg or build_pdg(submission.code, submission.language)
            compilation_failed = bool(details) and all(
                detail.result == "CE" for detail in details
            )
            compile_info = None
            if language.compile_cmd:
                compile_info = {
                    "result": "error" if compilation_failed else "success",
                    "message": "compilation failed" if compilation_failed else "",
                }
            run_info = {
                "result": "not_started" if compilation_failed else "finished",
                "message": (
                    "program was not run because compilation failed"
                    if compilation_failed
                    else f"{len(details)} test cases finished"
                ),
            }

            # 将测例结果、总分、编译运行摘要和 PDG 写回提交并刷新用户统计。
            def finish(current):
                for item in current["submissions"]:
                    if item["submission_id"] == submission_id:
                        item.update(
                            status="success",
                            details=[detail.model_dump(mode="json") for detail in details],
                            score=score,
                            counts=len(problem.testcases) * 10,
                            pdg=pdg,
                            compile_info=compile_info,
                            run_info=run_info,
                            error_info="",
                        )
                        break
                recompute_user_stats(current)

            await self.store.mutate(finish)
        except Exception:
            logger.exception("Evaluation failed for submission %s", submission_id)

            # 后台评测出现系统异常时记录 error 终态，供前端与日志区分代码错误。
            def fail(state):
                for item in state["submissions"]:
                    if item["submission_id"] == submission_id:
                        item.update(
                            status="error",
                            compile_info=None,
                            run_info={
                                "result": "error",
                                "message": "judge task failed",
                            },
                            error_info="judge task failed; check server logs",
                        )
                        break
                recompute_user_stats(state)

            await self.store.mutate(fail)

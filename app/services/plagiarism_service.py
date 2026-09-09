"""Background PDG construction, similarity matching, and reports."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.exceptions import ApiError
from app.models.plagiarism import (
    PlagiarismMatch,
    PlagiarismRequest,
    PlagiarismTask,
)
from app.models.submission import Submission
from app.plagiarism.pdg import build_pdg, graph_similarity, map_similar_nodes
from app.repositories.state_store import StateStore
from app.services.state_helpers import next_numeric_id


logger = logging.getLogger(__name__)


class PlagiarismService:
    # 保存状态仓库并追踪当前进程中的查重后台任务，便于关闭时统一取消。
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self._tasks: set[asyncio.Task] = set()

    # 校验题目存在、持久化 pending 任务，再异步计算该题全部提交对。
    async def start(self, payload: PlagiarismRequest) -> PlagiarismTask:
        now = datetime.now(timezone.utc).isoformat()

        # 在状态锁内校验题号、分配递增任务 ID 并追加 pending 记录。
        def create(state):
            if not any(item["id"] == payload.problem_id for item in state["problems"]):
                raise ApiError(404, "problem not found")
            task = PlagiarismTask(
                task_id=next_numeric_id(state["plagiarism_tasks"], "task_id"),
                problem_id=payload.problem_id,
                threshold=payload.threshold,
                created_at=now,
            )
            state["plagiarism_tasks"].append(task.model_dump(mode="json"))
            return task

        task = await self.store.mutate(create)
        background = asyncio.create_task(self._analyze(task.task_id))
        self._tasks.add(background)
        background.add_done_callback(self._tasks.discard)
        return task

    # 应用重启或数据导入后，为每条 pending 查重记录重新创建后台任务。
    async def resume_pending(self) -> None:
        state = await self.store.read()
        for item in state["plagiarism_tasks"]:
            if item.get("status") != "pending":
                continue
            background = asyncio.create_task(self._analyze(str(item["task_id"])))
            self._tasks.add(background)
            background.add_done_callback(self._tasks.discard)

    # 取消并等待当前进程中的全部查重 Task，避免退出时留下悬挂任务。
    async def shutdown(self) -> None:
        tasks = list(self._tasks)
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # 按任务 ID 读取并验证完整查重状态，不存在时返回 404。
    async def get(self, task_id: str) -> PlagiarismTask:
        state = await self.store.read()
        raw = next(
            (item for item in state["plagiarism_tasks"] if item["task_id"] == task_id),
            None,
        )
        if raw is None:
            raise ApiError(404, "plagiarism task not found")
        return PlagiarismTask.model_validate(raw)

    # 仅为已结束且报告文件真实存在的任务返回下载路径。
    async def report_path(self, task_id: str) -> Path:
        task = await self.get(task_id)
        if task.status == "pending":
            raise ApiError(400, "plagiarism task is still pending")
        path = self.store.report_dir / f"plagiarism-{task_id}.json"
        if not path.is_file():
            raise ApiError(404, "plagiarism report not found")
        return path

    # 构造/复用 PDG，比较每一对提交，写报告后再原子发布 success 状态。
    async def _analyze(self, task_id: str) -> None:
        try:
            state = await self.store.read()
            raw_task = next(
                item for item in state["plagiarism_tasks"] if item["task_id"] == task_id
            )
            task = PlagiarismTask.model_validate(raw_task)
            submissions = [
                Submission.model_validate(item)
                for item in state["submissions"]
                if item["problem_id"] == task.problem_id
            ]
            graphs = {
                item.submission_id: item.pdg or build_pdg(item.code, item.language)
                for item in submissions
            }
            matches: list[PlagiarismMatch] = []
            for left_index, left in enumerate(submissions):
                for right in submissions[left_index + 1 :]:
                    similarity = graph_similarity(
                        graphs[left.submission_id], graphs[right.submission_id]
                    )
                    matches.append(
                        PlagiarismMatch(
                            left_submission_id=left.submission_id,
                            right_submission_id=right.submission_id,
                            similarity=similarity,
                            is_clone=similarity >= task.threshold,
                            node_mapping=map_similar_nodes(
                                graphs[left.submission_id],
                                graphs[right.submission_id],
                            ),
                        )
                    )
            matches.sort(key=lambda item: item.similarity, reverse=True)

            report = {
                "task_id": task_id,
                "problem_id": task.problem_id,
                "threshold": task.threshold,
                "summary": {
                    "submission_count": len(submissions),
                    "pair_count": len(matches),
                    "clone_count": sum(match.is_clone for match in matches),
                },
                "matches": [match.model_dump(mode="json") for match in matches],
            }
            self.store.report_dir.mkdir(parents=True, exist_ok=True)
            path = self.store.report_dir / f"plagiarism-{task_id}.json"
            temporary = path.with_suffix(".json.tmp")
            await asyncio.to_thread(
                temporary.write_text,
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            await asyncio.to_thread(temporary.replace, path)

            # 持久化各提交的 PDG 以及任务的匹配列表和汇总计数。
            def finish(current):
                for submission in current["submissions"]:
                    if submission["submission_id"] in graphs:
                        submission["pdg"] = graphs[submission["submission_id"]]
                for item in current["plagiarism_tasks"]:
                    if item["task_id"] == task_id:
                        item.update(
                            status="success",
                            matches=[match.model_dump(mode="json") for match in matches],
                            submission_count=len(submissions),
                            pair_count=len(matches),
                            clone_count=sum(match.is_clone for match in matches),
                        )

            # 只有可下载的报告生成后，才发布成功状态。
            await self.store.mutate(finish)
        except Exception:
            logger.exception("Plagiarism analysis failed for task %s", task_id)

            # 捕获后台分析异常后将对应任务标为 error，防止永久停在 pending。
            def fail(state):
                for item in state["plagiarism_tasks"]:
                    if item["task_id"] == task_id:
                        item["status"] = "error"

            await self.store.mutate(fail)

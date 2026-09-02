"""Background PDG construction, similarity matching, and reports."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.exceptions import ApiError
from app.models.plagiarism import (
    PlagiarismMatch,
    PlagiarismRequest,
    PlagiarismTask,
)
from app.models.submission import Submission
from app.plagiarism.pdg import build_pdg, graph_similarity
from app.repositories.state_store import StateStore
from app.services.state_helpers import next_numeric_id


class PlagiarismService:
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self._tasks: set[asyncio.Task] = set()

    async def start(self, payload: PlagiarismRequest) -> PlagiarismTask:
        now = datetime.now(timezone.utc).isoformat()

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

    async def resume_pending(self) -> None:
        state = await self.store.read()
        for item in state["plagiarism_tasks"]:
            if item.get("status") != "pending":
                continue
            background = asyncio.create_task(self._analyze(str(item["task_id"])))
            self._tasks.add(background)
            background.add_done_callback(self._tasks.discard)

    async def shutdown(self) -> None:
        tasks = list(self._tasks)
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def get(self, task_id: str) -> PlagiarismTask:
        state = await self.store.read()
        raw = next(
            (item for item in state["plagiarism_tasks"] if item["task_id"] == task_id),
            None,
        )
        if raw is None:
            raise ApiError(404, "plagiarism task not found")
        return PlagiarismTask.model_validate(raw)

    async def report_path(self, task_id: str) -> Path:
        task = await self.get(task_id)
        if task.status == "pending":
            raise ApiError(400, "plagiarism task is still pending")
        path = self.store.report_dir / f"plagiarism-{task_id}.json"
        if not path.is_file():
            raise ApiError(404, "plagiarism report not found")
        return path

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
                        )
                    )
            matches.sort(key=lambda item: item.similarity, reverse=True)

            def finish(current):
                for submission in current["submissions"]:
                    if submission["submission_id"] in graphs:
                        submission["pdg"] = graphs[submission["submission_id"]]
                for item in current["plagiarism_tasks"]:
                    if item["task_id"] == task_id:
                        item.update(
                            status="success",
                            matches=[match.model_dump(mode="json") for match in matches],
                        )

            await self.store.mutate(finish)
            report = {
                "task_id": task_id,
                "problem_id": task.problem_id,
                "threshold": task.threshold,
                "matches": [match.model_dump(mode="json") for match in matches],
            }
            self.store.report_dir.mkdir(parents=True, exist_ok=True)
            path = self.store.report_dir / f"plagiarism-{task_id}.json"
            await asyncio.to_thread(
                path.write_text,
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            def fail(state):
                for item in state["plagiarism_tasks"]:
                    if item["task_id"] == task_id:
                        item["status"] = "error"

            await self.store.mutate(fail)

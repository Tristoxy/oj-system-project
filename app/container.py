"""Application service container."""

from pathlib import Path

from app.core.config import judge_backend
from app.judge.runner import JudgeRunner
from app.repositories.state_store import StateStore
from app.services.ai_service import AIProblemService
from app.services.auth_service import AuthService
from app.services.language_service import LanguageService
from app.services.log_service import LogService
from app.services.plagiarism_service import PlagiarismService
from app.services.problem_service import ProblemService
from app.services.submission_service import SubmissionService
from app.services.system_service import SystemService
from app.services.user_service import UserService


class AppContainer:
    # 函数 `__init__`：负责当前模块中的对应操作。
    def __init__(self, data_dir: Path) -> None:
        self.store = StateStore(data_dir)
        self.system = SystemService(self.store)
        self.auth = AuthService(self.store)
        self.users = UserService(self.store)
        self.problems = ProblemService(self.store)
        self.languages = LanguageService(self.store)
        self.logs = LogService(self.store)
        self.ai = AIProblemService(self.store)
        self.runner = JudgeRunner(judge_backend(), self.store.spj_dir)
        self.submissions = SubmissionService(self.store, self.runner)
        self.plagiarism = PlagiarismService(self.store)

    # 函数 `initialize`：负责当前模块中的对应操作。
    async def initialize(self) -> None:
        await self.system.initialize()
        await self.submissions.resume_pending()
        await self.plagiarism.resume_pending()

    # 函数 `cancel_background_tasks`：负责当前模块中的对应操作。
    async def cancel_background_tasks(self) -> None:
        await self.submissions.shutdown()
        await self.plagiarism.shutdown()
        await self.ai.shutdown()

    # 函数 `close`：负责当前模块中的对应操作。
    async def close(self) -> None:
        await self.cancel_background_tasks()

"""Application service container."""

from pathlib import Path

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
    # 围绕同一个 StateStore 组装评测器和全部业务服务，保证它们共享一致的数据状态。
    def __init__(self, data_dir: Path) -> None:
        self.store = StateStore(data_dir)
        self.system = SystemService(self.store)
        self.auth = AuthService(self.store)
        self.users = UserService(self.store)
        self.problems = ProblemService(self.store)
        self.languages = LanguageService(self.store)
        self.logs = LogService(self.store)
        self.ai = AIProblemService(self.store)
        self.runner = JudgeRunner(self.store.spj_dir)
        self.submissions = SubmissionService(self.store, self.runner)
        self.plagiarism = PlagiarismService(self.store)

    # 初始化持久化数据，并恢复上次退出时仍处于 pending 的评测和查重任务。
    async def initialize(self) -> None:
        await self.system.initialize()
        await self.submissions.resume_pending()
        await self.plagiarism.resume_pending()

    # 取消评测、查重和 AI 命题后台任务，供重置、导入和进程退出前统一清理。
    async def cancel_background_tasks(self) -> None:
        await self.submissions.shutdown()
        await self.plagiarism.shutdown()
        await self.ai.shutdown()

    # 执行应用生命周期的关闭清理；当前只需停止全部后台任务。
    async def close(self) -> None:
        await self.cancel_background_tasks()

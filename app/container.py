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
    # 所有系统组件
    # 围绕同一个 StateStore 组装评测器和全部业务服务，保证它们共享一致的数据状态。
    def __init__(self, data_dir: Path) -> None:
        self.store = StateStore(data_dir) # 数据存储
        self.system = SystemService(self.store) # 系统服务（默认管理员、语言）
        self.auth = AuthService(self.store) # 认证服务（登录、登出、session、用户）
        self.users = UserService(self.store) # 创建用户
        self.problems = ProblemService(self.store) # 创建题目
        self.languages = LanguageService(self.store) # 创建语言
        self.logs = LogService(self.store) # 创建日志
        self.ai = AIProblemService(self.store) # 创建ai
        self.runner = JudgeRunner(self.store.spj_dir) # 创建评测器
        self.submissions = SubmissionService(self.store, self.runner) # 创建提交服务（提交结果、执行用户代码）
        self.plagiarism = PlagiarismService(self.store) # 创建查重

    # 初始化持久化数据，并恢复上次退出时仍处于 pending 的评测和查重任务。
    async def initialize(self) -> None:
        await self.system.initialize()
        await self.submissions.resume_pending()
        await self.plagiarism.resume_pending()

    # 恢复未完成的提交、查重任务
    # 取消评测、查重和 AI 命题后台任务，供重置、导入和进程退出前统一清理。
    async def cancel_background_tasks(self) -> None:
        await self.submissions.shutdown()
        await self.plagiarism.shutdown()
        await self.ai.shutdown()

    # 执行应用生命周期的关闭清理；当前只需停止全部后台任务。
    async def close(self) -> None:
        await self.cancel_background_tasks()

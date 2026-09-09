"""Initialization, reset, export, and validated import."""

from datetime import datetime, timezone

from app.core.exceptions import ApiError
from app.core.security import hash_password, is_password_hash
from app.models.language import Language
from app.models.problem import Problem
from app.models.submission import Submission
from app.models.system import ImportBundle
from app.models.user import User
from app.plagiarism.pdg import build_pdg
from app.repositories.state_store import StateStore, empty_state
from app.services.state_helpers import next_numeric_id, recompute_user_stats


DEFAULT_LANGUAGES = [
    Language(
        name="python",
        file_ext=".py",
        run_cmd="python3 {src}",
        time_limit=3.0,
        memory_limit=128,
    ),
    Language(
        name="cpp",
        file_ext=".cpp",
        compile_cmd="g++ {src} -O2 -std=c++14 -o {exe}",
        run_cmd="{exe}",
        time_limit=3.0,
        memory_limit=128,
    ),
]

DEFAULT_PROBLEMS = [
    Problem(
        id="1001",
        title="两数之和",
        description="给定两个整数，输出它们的和。",
        input_description="输入一行两个整数 a 和 b。",
        output_description="输出 a+b。",
        samples=[{"input": "1 2\n", "output": "3\n"}],
        constraints="-10^9 <= a,b <= 10^9",
        testcases=[
            {"input": "1 2\n", "output": "3\n"},
            {"input": "-5 8\n", "output": "3\n"},
            {"input": "1000000000 1000000000\n", "output": "2000000000\n"},
        ],
        hint="读取两个整数后相加。",
        source="课程演示",
        tags=["基础", "算术"],
        time_limit=3.0,
        memory_limit=128,
        author="Tristoxy",
        difficulty="入门",
    ),
    Problem(
        id="1002",
        title="两数之差",
        description="给定两个整数，输出第一个整数减去第二个整数的结果。",
        input_description="输入一行两个整数 a 和 b。",
        output_description="输出 a-b。",
        samples=[{"input": "5 2\n", "output": "3\n"}],
        constraints="-10^9 <= a,b <= 10^9",
        testcases=[
            {"input": "5 2\n", "output": "3\n"},
            {"input": "-5 8\n", "output": "-13\n"},
            {"input": "1000000000 -1000000000\n", "output": "2000000000\n"},
        ],
        hint="注意运算顺序是 a-b。",
        source="课程演示",
        tags=["基础", "算术"],
        time_limit=3.0,
        memory_limit=128,
        author="Tristoxy",
        difficulty="入门",
    ),
    Problem(
        id="1003",
        title="两数之积",
        description="给定两个整数，输出它们的乘积。",
        input_description="输入一行两个整数 a 和 b。",
        output_description="输出 a*b。",
        samples=[{"input": "3 4\n", "output": "12\n"}],
        constraints="-10^9 <= a,b <= 10^9",
        testcases=[
            {"input": "3 4\n", "output": "12\n"},
            {"input": "-5 8\n", "output": "-40\n"},
            {"input": "100000 100000\n", "output": "10000000000\n"},
        ],
        hint="Python 整数可以直接处理这里的乘法范围。",
        source="课程演示",
        tags=["基础", "算术"],
        time_limit=3.0,
        memory_limit=128,
        author="Tristoxy",
        difficulty="入门",
    ),
]


class SystemService:
    # 保存共享状态仓库，统一负责初始数据、重置以及课程数据包导入导出。
    def __init__(self, store: StateStore) -> None:
        self.store = store

    # 初始化状态文件，迁移旧管理员账号，并补齐默认语言和 1001–1003 三道题。
    async def initialize(self) -> None:
        await self.store.initialize()

        # 在状态锁内执行幂等默认数据迁移，已有同名语言或题号不会重复添加。
        def add_defaults(state):
            if not any(user.get("username") == "Tristoxy" for user in state["users"]):
                legacy_admin = next(
                    (
                        user
                        for user in state["users"]
                        if user.get("username") == "admin" and user.get("role") == "admin"
                    ),
                    None,
                )
                if legacy_admin is not None:
                    legacy_admin["username"] = "Tristoxy"
                    legacy_admin["password"] = hash_password("Qtc521521")
                else:
                    initial_admin = self._initial_admin()
                    if any(user.get("user_id") == "1" for user in state["users"]):
                        initial_admin.user_id = next_numeric_id(state["users"], "user_id")
                    state["users"].append(initial_admin.model_dump(mode="json"))
            known = {language.get("name") for language in state["languages"]}
            for language in DEFAULT_LANGUAGES:
                if language.name not in known:
                    state["languages"].append(language.model_dump(mode="json"))
            known_problem_ids = {problem.get("id") for problem in state["problems"]}
            for problem in DEFAULT_PROBLEMS:
                if problem.id not in known_problem_ids:
                    state["problems"].append(problem.model_dump(mode="json"))

        await self.store.mutate(add_defaults)

    # 用空状态覆盖全部集合、清理衍生文件，再重新创建系统默认数据。
    async def reset(self) -> None:
        await self.store.replace(empty_state())
        await self.store.clear_files()
        await self.initialize()

    # 重新计算用户统计并导出课程规定的 users/problems/submissions 固定结构。
    async def export_data(self) -> dict[str, object]:
        state = await self.store.read()
        recompute_user_stats(state)
        users = [User.model_validate(item).model_dump(mode="json") for item in state["users"]]
        problems = [
            Problem.model_validate(item).model_dump(mode="json") for item in state["problems"]
        ]
        submissions = [
            Submission.model_validate(item).model_dump(
                mode="json",
                exclude={
                    "created_at",
                    "pdg",
                    "judge_snapshot",
                    "compile_info",
                    "run_info",
                    "error_info",
                },
            )
            for item in state["submissions"]
        ]
        return {"users": users, "problems": problems, "submissions": submissions}

    # 以新数据覆盖同 ID 旧数据、补建 PDG、清除会话并刷新用户统计。
    async def import_data(self, bundle: ImportBundle) -> None:
        # 在一个原子状态修改中再次校验引用并合并三类课程数据。
        def merge(state):
            self._validate_import_against_state(bundle, state)
            imported_users = [item.model_dump(mode="json") for item in bundle.users]
            imported_problems = [item.model_dump(mode="json") for item in bundle.problems]
            self._merge(state["users"], imported_users, "user_id")
            self._merge(state["problems"], imported_problems, "id")
            imported_submissions = []
            for item in bundle.submissions:
                raw = item.model_dump(mode="json")
                raw["pdg"] = build_pdg(item.code, item.language)
                imported_submissions.append(raw)
            self._merge(state["submissions"], imported_submissions, "submission_id")
            state["sessions"] = []
            recompute_user_stats(state)

        await self.store.mutate(merge)

    # 在暂停后台任务之前先完整预检导入包，避免无效文件影响正在运行的任务。
    async def validate_import(self, bundle: ImportBundle) -> None:
        """Validate completely before the caller pauses background workers."""
        state = await self.store.read()
        self._validate_import_against_state(bundle, state)

    # 校验哈希、包内唯一性、合并后用户名唯一性以及提交的用户/题目外键。
    @staticmethod
    def _validate_import_against_state(
        bundle: ImportBundle,
        state: dict[str, list[dict]],
    ) -> None:
        # 检查同一字段值在导入包内是否重复，并转成统一的 400 业务错误。
        def require_unique(values: list[str], label: str) -> None:
            if len(values) != len(set(values)):
                raise ApiError(400, f"duplicate {label} in import data")

        for user in bundle.users:
            if not is_password_hash(user.password):
                raise ApiError(400, "imported passwords must be valid hashes")

        require_unique([user.user_id for user in bundle.users], "user_id")
        require_unique([user.username for user in bundle.users], "username")
        require_unique([problem.id for problem in bundle.problems], "problem id")
        require_unique(
            [submission.submission_id for submission in bundle.submissions],
            "submission_id",
        )

        merged_users = {str(item["user_id"]): item for item in state["users"]}
        merged_users.update(
            {user.user_id: user.model_dump(mode="json") for user in bundle.users}
        )
        usernames = [str(item["username"]) for item in merged_users.values()]
        require_unique(usernames, "username")

        problem_ids = {str(item["id"]) for item in state["problems"]}
        problem_ids.update(problem.id for problem in bundle.problems)
        for submission in bundle.submissions:
            if submission.user_id not in merged_users:
                raise ApiError(400, "submission references an unknown user")
            if submission.problem_id not in problem_ids:
                raise ApiError(400, "submission references an unknown problem")

    # 按指定主键执行 upsert：已存在则原位替换，否则追加到集合末尾。
    @staticmethod
    def _merge(target: list[dict], incoming: list[dict], key: str) -> None:
        indexes = {item[key]: index for index, item in enumerate(target)}
        for item in incoming:
            if item[key] in indexes:
                target[indexes[item[key]]] = item
            else:
                target.append(item)

    # 构造题目要求的初始管理员，并在创建时立即哈希固定初始密码。
    @staticmethod
    def _initial_admin() -> User:
        return User(
            user_id="1",
            username="Tristoxy",
            password=hash_password("Qtc521521"),
            role="admin",
            join_time=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )

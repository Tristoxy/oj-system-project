"""Thread-safe, atomic JSON persistence for the complete OJ state."""

import asyncio
import copy
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar


T = TypeVar("T")
# 数据表
COLLECTIONS = (
    "users",
    "problems",
    "languages",
    "submissions",
    "sessions",
    "access_logs",
    "plagiarism_tasks",
)


# 为每个持久化集合创建独立空列表，作为首次启动和系统重置的初始状态。
def empty_state() -> dict[str, list[dict[str, Any]]]:
    return {name: [] for name in COLLECTIONS}

# json数据库的操作对象
class StateStore:
    # 创建锁，用于防止多个请求同时写json导致数据冲突
    # 根据数据根目录确定状态、SPJ 和查重报告路径，并创建进程内重入锁。
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.state_file = data_dir / "state.json"
        self.spj_dir = data_dir / "spj"
        self.report_dir = data_dir / "reports"
        self._lock = threading.RLock()

    # 在线程池中创建数据目录和首次启动所需的空状态文件。
    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    # 读取数据
    # 在线程池中加锁读取状态，并返回深拷贝以防调用者绕过持久化修改数据。
    async def read(self) -> dict[str, list[dict[str, Any]]]:
        return await asyncio.to_thread(self._read_sync)

    # 数据修改
    # 在线程池和同一把锁内执行“读取—修改—原子写回”，并返回操作结果副本。
    async def mutate(self, operation: Callable[[dict[str, list[dict[str, Any]]]], T]) -> T:
        return await asyncio.to_thread(self._mutate_sync, operation)

    # 用经过集合规范化的完整状态替换现有 state.json，主要用于系统重置。
    async def replace(self, state: dict[str, list[dict[str, Any]]]) -> None:
        await asyncio.to_thread(self._replace_sync, state)

    # 删除 SPJ 和查重报告目录中的普通文件，但保留目录本身。
    async def clear_files(self) -> None:
        await asyncio.to_thread(self._clear_files_sync)

    # 执行阻塞式目录初始化；state.json 不存在时以空集合写入。
    def _initialize_sync(self) -> None:
        with self._lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.spj_dir.mkdir(parents=True, exist_ok=True)
            self.report_dir.mkdir(parents=True, exist_ok=True)
            if not self.state_file.exists():
                self._write_unlocked(empty_state())

    # 读取并校验 JSON 根对象及各集合类型，缺失的新增集合自动补为空列表。
    def _load_unlocked(self) -> dict[str, list[dict[str, Any]]]:
        if not self.state_file.exists():
            return empty_state()
        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state root must be an object")
        result = empty_state()
        for name in COLLECTIONS:
            value = data.get(name, [])
            if not isinstance(value, list):
                raise ValueError(f"state collection {name} must be a list")
            result[name] = value
        return result

    # 先写同目录临时文件再 replace，避免进程中断留下半个 JSON 文件。
    def _write_unlocked(self, state: dict[str, list[dict[str, Any]]]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.state_file)

    # 在锁内加载状态并深拷贝，作为异步 read 的阻塞实现。
    def _read_sync(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            return copy.deepcopy(self._load_unlocked())

    # 在单次临界区内执行修改回调和落盘，避免并发请求互相覆盖。
    def _mutate_sync(self, operation: Callable[[dict[str, list[dict[str, Any]]]], T]) -> T:
        with self._lock:
            state = self._load_unlocked()
            result = operation(state)
            self._write_unlocked(state)
            return copy.deepcopy(result)

    # 只接受已知集合并深拷贝其内容，然后原子覆盖完整状态文件。
    def _replace_sync(self, state: dict[str, list[dict[str, Any]]]) -> None:
        with self._lock:
            normalized = empty_state()
            for name in COLLECTIONS:
                value = state.get(name, [])
                if not isinstance(value, list):
                    raise ValueError(f"state collection {name} must be a list")
                normalized[name] = copy.deepcopy(value)
            self._write_unlocked(normalized)

    # 在锁内逐个清理可再生成的 SPJ 与报告文件，忽略目录等非文件项目。
    def _clear_files_sync(self) -> None:
        with self._lock:
            for directory in (self.spj_dir, self.report_dir):
                directory.mkdir(parents=True, exist_ok=True)
                for path in directory.iterdir():
                    if path.is_file():
                        path.unlink()

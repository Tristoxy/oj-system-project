"""Thread-safe, atomic JSON persistence for the complete OJ state."""

import asyncio
import copy
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar


T = TypeVar("T")
COLLECTIONS = (
    "users",
    "problems",
    "languages",
    "submissions",
    "sessions",
    "access_logs",
    "plagiarism_tasks",
)


# 函数 `empty_state`：负责当前模块中的对应操作。
def empty_state() -> dict[str, list[dict[str, Any]]]:
    return {name: [] for name in COLLECTIONS}


class StateStore:
    # 函数 `__init__`：负责当前模块中的对应操作。
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.state_file = data_dir / "state.json"
        self.spj_dir = data_dir / "spj"
        self.report_dir = data_dir / "reports"
        self._lock = threading.RLock()

    # 函数 `initialize`：负责当前模块中的对应操作。
    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    # 函数 `read`：负责当前模块中的对应操作。
    async def read(self) -> dict[str, list[dict[str, Any]]]:
        return await asyncio.to_thread(self._read_sync)

    # 函数 `mutate`：负责当前模块中的对应操作。
    async def mutate(self, operation: Callable[[dict[str, list[dict[str, Any]]]], T]) -> T:
        return await asyncio.to_thread(self._mutate_sync, operation)

    # 函数 `replace`：负责当前模块中的对应操作。
    async def replace(self, state: dict[str, list[dict[str, Any]]]) -> None:
        await asyncio.to_thread(self._replace_sync, state)

    # 函数 `clear_files`：负责当前模块中的对应操作。
    async def clear_files(self) -> None:
        await asyncio.to_thread(self._clear_files_sync)

    # 函数 `_initialize_sync`：负责当前模块中的对应操作。
    def _initialize_sync(self) -> None:
        with self._lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.spj_dir.mkdir(parents=True, exist_ok=True)
            self.report_dir.mkdir(parents=True, exist_ok=True)
            if not self.state_file.exists():
                self._write_unlocked(empty_state())

    # 函数 `_load_unlocked`：负责当前模块中的对应操作。
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

    # 函数 `_write_unlocked`：负责当前模块中的对应操作。
    def _write_unlocked(self, state: dict[str, list[dict[str, Any]]]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.state_file)

    # 函数 `_read_sync`：负责当前模块中的对应操作。
    def _read_sync(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            return copy.deepcopy(self._load_unlocked())

    # 函数 `_mutate_sync`：负责当前模块中的对应操作。
    def _mutate_sync(self, operation: Callable[[dict[str, list[dict[str, Any]]]], T]) -> T:
        with self._lock:
            state = self._load_unlocked()
            result = operation(state)
            self._write_unlocked(state)
            return copy.deepcopy(result)

    # 函数 `_replace_sync`：负责当前模块中的对应操作。
    def _replace_sync(self, state: dict[str, list[dict[str, Any]]]) -> None:
        with self._lock:
            normalized = empty_state()
            for name in COLLECTIONS:
                value = state.get(name, [])
                if not isinstance(value, list):
                    raise ValueError(f"state collection {name} must be a list")
                normalized[name] = copy.deepcopy(value)
            self._write_unlocked(normalized)

    # 函数 `_clear_files_sync`：负责当前模块中的对应操作。
    def _clear_files_sync(self) -> None:
        with self._lock:
            for directory in (self.spj_dir, self.report_dir):
                directory.mkdir(parents=True, exist_ok=True)
                for path in directory.iterdir():
                    if path.is_file():
                        path.unlink()

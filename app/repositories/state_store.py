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


def empty_state() -> dict[str, list[dict[str, Any]]]:
    return {name: [] for name in COLLECTIONS}


class StateStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.state_file = data_dir / "state.json"
        self.spj_dir = data_dir / "spj"
        self.report_dir = data_dir / "reports"
        self._lock = threading.RLock()

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def read(self) -> dict[str, list[dict[str, Any]]]:
        return await asyncio.to_thread(self._read_sync)

    async def mutate(self, operation: Callable[[dict[str, list[dict[str, Any]]]], T]) -> T:
        return await asyncio.to_thread(self._mutate_sync, operation)

    async def replace(self, state: dict[str, list[dict[str, Any]]]) -> None:
        await asyncio.to_thread(self._replace_sync, state)

    async def clear_files(self) -> None:
        await asyncio.to_thread(self._clear_files_sync)

    def _initialize_sync(self) -> None:
        with self._lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.spj_dir.mkdir(parents=True, exist_ok=True)
            self.report_dir.mkdir(parents=True, exist_ok=True)
            if not self.state_file.exists():
                self._write_unlocked(empty_state())

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

    def _write_unlocked(self, state: dict[str, list[dict[str, Any]]]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.state_file)

    def _read_sync(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            return copy.deepcopy(self._load_unlocked())

    def _mutate_sync(self, operation: Callable[[dict[str, list[dict[str, Any]]]], T]) -> T:
        with self._lock:
            state = self._load_unlocked()
            result = operation(state)
            self._write_unlocked(state)
            return copy.deepcopy(result)

    def _replace_sync(self, state: dict[str, list[dict[str, Any]]]) -> None:
        with self._lock:
            normalized = empty_state()
            for name in COLLECTIONS:
                value = state.get(name, [])
                if not isinstance(value, list):
                    raise ValueError(f"state collection {name} must be a list")
                normalized[name] = copy.deepcopy(value)
            self._write_unlocked(normalized)

    def _clear_files_sync(self) -> None:
        with self._lock:
            for directory in (self.spj_dir, self.report_dir):
                directory.mkdir(parents=True, exist_ok=True)
                for path in directory.iterdir():
                    if path.is_file():
                        path.unlink()

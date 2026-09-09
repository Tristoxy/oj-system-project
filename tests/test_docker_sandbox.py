"""Advance 3 command construction tests that do not require a Docker daemon."""

import asyncio
import os
from pathlib import Path

import pytest

from app.judge.runner import JudgeRunner, ProcessResult
from app.models.language import Language


# 函数 `test_docker_runner_applies_isolation_flags`：负责当前测试或测试夹具。
def test_docker_runner_applies_isolation_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = JudgeRunner("docker", tmp_path)
    language = Language(
        name="python",
        file_ext=".py",
        run_cmd="python3 {src}",
        time_limit=1,
        memory_limit=64,
    )
    source = tmp_path / "Main.py"
    source.write_text("print(1)", encoding="utf-8")
    captured: dict[str, object] = {}

    # 函数 `fake_execute`：负责当前测试或测试夹具。
    async def fake_execute(*args, **kwargs):
        captured["args"] = args[0]
        captured["kwargs"] = kwargs
        return ProcessResult("AC")

    monkeypatch.setattr(runner, "_execute", fake_execute)
    asyncio.run(
        runner._run_command(
            language.run_cmd,
            source,
            tmp_path / "Main",
            tmp_path,
            "",
            1,
            64,
            language,
        )
    )

    command = captured["args"]
    assert "--interactive" in command
    assert "--network=none" in command
    assert "--memory=64m" in command
    assert "--memory-swap=64m" in command
    assert "--cpus=1" in command
    assert "--pids-limit=64" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--read-only" in command
    assert "oj-python:3.10" in command
    container_name = next(
        item.removeprefix("--name=") for item in command if item.startswith("--name=")
    )
    assert container_name.startswith("oj-")
    assert captured["kwargs"] == {
        "use_process_limit": False,
        "docker_container": container_name,
    }


# 函数 `test_timed_out_docker_client_triggers_container_cleanup`：负责当前测试或测试夹具。
def test_timed_out_docker_client_triggers_container_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = JudgeRunner("docker", tmp_path)
    cleaned: list[str] = []

    # 函数 `fake_cleanup`：负责当前测试或测试夹具。
    async def fake_cleanup(name: str) -> None:
        cleaned.append(name)

    monkeypatch.setattr(runner, "_kill_docker_container", fake_cleanup)
    result = asyncio.run(
        runner._execute(
            ["python3", "-c", "import time; time.sleep(2)"],
            "",
            0.05,
            128,
            tmp_path,
            use_process_limit=False,
            docker_container="oj-test-container",
        )
    )

    assert result.result == "TLE"
    assert cleaned == ["oj-test-container"]


# 函数 `test_local_runner_kills_descendants_after_parent_exits`：负责当前测试或测试夹具。
@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX process groups")
def test_local_runner_kills_descendants_after_parent_exits(tmp_path: Path) -> None:
    marker = tmp_path / "orphan-marker"
    script = f"""
import os
import time

child = os.fork()
if child == 0:
    os.close(0)
    os.close(1)
    os.close(2)
    time.sleep(0.3)
    with open({str(marker)!r}, "w", encoding="utf-8") as output:
        output.write("leaked")
    os._exit(0)
print("parent finished")
"""

    # 函数 `run`：负责当前测试或测试夹具。
    async def run() -> ProcessResult:
        runner = JudgeRunner("local", tmp_path)
        result = await runner._execute(
            ["python3", "-c", script],
            "",
            1,
            128,
            tmp_path,
        )
        await asyncio.sleep(0.5)
        return result

    result = asyncio.run(run())
    assert result.result == "AC"
    assert not marker.exists()

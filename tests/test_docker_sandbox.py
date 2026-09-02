"""Advance 3 command construction tests that do not require a Docker daemon."""

import asyncio
from pathlib import Path

import pytest

from app.judge.runner import JudgeRunner, ProcessResult
from app.models.language import Language


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
    assert "--network=none" in command
    assert "--memory=64m" in command
    assert "--cpus=1" in command
    assert "--pids-limit=64" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--read-only" in command
    assert "oj-python:3.10" in command
    assert captured["kwargs"] == {"use_process_limit": False}

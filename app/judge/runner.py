"""Local and Docker-backed code runner with resource limits."""

import asyncio
import os
import signal
import shlex
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.models.language import Language
from app.models.problem import Problem, TestCase
from app.models.submission import CaseResult, TestCaseResult


@dataclass
class ProcessResult:
    result: CaseResult
    stdout: str = ""
    stderr: str = ""
    elapsed: float = 0.0
    memory_mb: float = 0.0


class JudgeRunner:
    def __init__(self, backend: str, spj_dir: Path) -> None:
        self.backend = backend
        self.spj_dir = spj_dir

    async def judge(
        self,
        code: str,
        language: Language,
        problem: Problem,
    ) -> list[TestCaseResult]:
        with tempfile.TemporaryDirectory(prefix="oj-") as directory_text:
            directory = Path(directory_text)
            source = directory / f"Main{language.file_ext}"
            executable = directory / "Main"
            source.write_text(code, encoding="utf-8")
            if self._uses_docker(language):
                os.chmod(directory, 0o777)

            if language.compile_cmd:
                compile_result = await self._run_command(
                    language.compile_cmd,
                    source,
                    executable,
                    directory,
                    "",
                    min(max(problem.time_limit * 5, 5), 30),
                    max(problem.memory_limit, language.memory_limit),
                    language,
                )
                if compile_result.result != "AC":
                    return [
                        TestCaseResult(
                            id=index,
                            result="CE",
                            time=round(compile_result.elapsed, 4),
                            memory=round(compile_result.memory_mb, 2),
                        )
                        for index in range(1, len(problem.testcases) + 1)
                    ]

            results: list[TestCaseResult] = []
            for index, testcase in enumerate(problem.testcases, start=1):
                run_result = await self._run_command(
                    language.run_cmd,
                    source,
                    executable,
                    directory,
                    testcase.input,
                    problem.time_limit,
                    problem.memory_limit,
                    language,
                )
                result = run_result.result
                if result == "AC":
                    result = await self._compare_output(
                        problem,
                        testcase,
                        run_result.stdout,
                        directory,
                    )
                results.append(
                    TestCaseResult(
                        id=index,
                        result=result,
                        time=round(run_result.elapsed, 4),
                        memory=round(run_result.memory_mb, 2),
                    )
                )
            return results

    def _uses_docker(self, language: Language) -> bool:
        if self.backend == "local":
            return False
        if self.backend == "docker":
            return True
        return shutil.which("docker") is not None and language.name in {"python", "cpp"}

    async def _run_command(
        self,
        template: str,
        source: Path,
        executable: Path,
        directory: Path,
        stdin: str,
        timeout: float,
        memory_limit: int,
        language: Language,
    ) -> ProcessResult:
        docker = self._uses_docker(language)
        if docker:
            container_source = Path("/workspace") / source.name
            container_executable = Path("/workspace") / executable.name
            inner = shlex.split(
                template.format(src=str(container_source), exe=str(container_executable))
            )
            image = "python:3.10-slim" if language.name == "python" else "gcc:13"
            args = [
                "docker",
                "run",
                "--rm",
                "--network=none",
                f"--memory={memory_limit}m",
                "--cpus=1",
                "--pids-limit=64",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--read-only",
                "--tmpfs=/tmp:rw,noexec,nosuid,size=32m",
                f"--volume={directory}:/workspace:rw",
                "--workdir=/workspace",
                "--user=65534:65534",
                image,
                *inner,
            ]
            process_memory = memory_limit + 128
        else:
            args = shlex.split(template.format(src=str(source), exe=str(executable)))
            process_memory = memory_limit
        return await self._execute(args, stdin, timeout, process_memory, directory)

    async def _execute(
        self,
        args: list[str],
        stdin: str,
        timeout: float,
        memory_limit: int,
        cwd: Path,
    ) -> ProcessResult:
        started = time.perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            return ProcessResult("UNK", stderr=str(exc))

        monitor = asyncio.create_task(self._monitor_memory(process, memory_limit))
        communicate = asyncio.create_task(process.communicate(stdin.encode("utf-8")))
        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                asyncio.shield(communicate),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            timed_out = True
            self._kill_process_tree(process)
            stdout_bytes, stderr_bytes = await communicate
        except asyncio.CancelledError:
            self._kill_process_tree(process)
            await asyncio.gather(communicate, monitor, return_exceptions=True)
            raise
        memory_mb, memory_exceeded = await monitor
        await process.wait()
        elapsed = time.perf_counter() - started
        if memory_exceeded:
            result: CaseResult = "MLE"
        elif timed_out:
            result = "TLE"
        elif process.returncode in {137, -signal.SIGKILL} and self.backend == "docker":
            # Docker reports an OOM-killed container as SIGKILL/137.
            result = "MLE"
        elif process.returncode != 0:
            result = "RE"
        else:
            result = "AC"
        return ProcessResult(
            result=result,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            elapsed=elapsed,
            memory_mb=memory_mb,
        )

    async def _monitor_memory(
        self,
        process: asyncio.subprocess.Process,
        memory_limit: int,
    ) -> tuple[float, bool]:
        maximum = 0.0
        exceeded = False
        try:
            observed = psutil.Process(process.pid)
            while process.returncode is None:
                rss = observed.memory_info().rss
                for child in observed.children(recursive=True):
                    try:
                        rss += child.memory_info().rss
                    except psutil.Error:
                        pass
                maximum = max(maximum, rss / (1024**2))
                if maximum > memory_limit:
                    exceeded = True
                    self._kill_process_tree(process)
                    break
                await asyncio.sleep(0.01)
        except psutil.Error:
            pass
        return maximum, exceeded

    @staticmethod
    def _kill_process_tree(process: asyncio.subprocess.Process) -> None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except (ProcessLookupError, PermissionError):
            pass

    async def _compare_output(
        self,
        problem: Problem,
        testcase: TestCase,
        actual: str,
        directory: Path,
    ) -> CaseResult:
        if problem.judge_mode == "strict":
            return "AC" if actual == testcase.output else "WA"
        if problem.judge_mode == "spj":
            return await self._run_spj(problem.id, testcase, actual, directory)
        return "AC" if self._normalize(actual) == self._normalize(testcase.output) else "WA"

    async def _run_spj(
        self,
        problem_id: str,
        testcase: TestCase,
        actual: str,
        directory: Path,
    ) -> CaseResult:
        script = self.spj_dir / f"{problem_id}.py"
        if not script.is_file():
            return "UNK"
        input_path = directory / "spj-input.txt"
        expected_path = directory / "spj-expected.txt"
        actual_path = directory / "spj-actual.txt"
        input_path.write_text(testcase.input, encoding="utf-8")
        expected_path.write_text(testcase.output, encoding="utf-8")
        actual_path.write_text(actual, encoding="utf-8")
        result = await self._execute(
            [sys.executable, str(script), str(input_path), str(expected_path), str(actual_path)],
            "",
            2,
            64,
            directory,
        )
        return "AC" if result.result == "AC" else "WA"

    @staticmethod
    def _normalize(value: str) -> str:
        lines = [line.rstrip() for line in value.replace("\r\n", "\n").split("\n")]
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

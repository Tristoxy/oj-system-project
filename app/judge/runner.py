"""Local and Docker-backed code runner with resource limits."""

import asyncio
import os
import secrets
import signal
import shlex
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

try:
    import resource
except ImportError:  # pragma: no cover - resource is unavailable on Windows
    resource = None

from app.core.config import DEFAULT_MEMORY_LIMIT, DEFAULT_TIME_LIMIT
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
    MAX_OUTPUT_BYTES = 4 * 1024 * 1024

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

            time_limit, memory_limit = self._resolve_limits(problem, language)

            if language.compile_cmd:
                compile_result = await self._run_command(
                    language.compile_cmd,
                    source,
                    executable,
                    directory,
                    "",
                    min(max(time_limit * 5, 5), 30),
                    memory_limit,
                    language,
                )
                if compile_result.result != "AC":
                    compile_case_result: CaseResult = (
                        "UNK" if compile_result.result == "UNK" else "CE"
                    )
                    return [
                        TestCaseResult(
                            id=index,
                            result=compile_case_result,
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
                    time_limit,
                    memory_limit,
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

    @staticmethod
    def _resolve_limits(problem: Problem, language: Language) -> tuple[float, int]:
        """Resolve problem, language, then system defaults as clarified by course staff."""
        time_limit = problem.time_limit
        if time_limit is None:
            time_limit = language.time_limit
        if time_limit is None:
            time_limit = DEFAULT_TIME_LIMIT

        memory_limit = problem.memory_limit
        if memory_limit is None:
            memory_limit = language.memory_limit
        if memory_limit is None:
            memory_limit = DEFAULT_MEMORY_LIMIT
        return time_limit, memory_limit

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
        container_name: str | None = None
        if docker:
            container_source = Path("/workspace") / source.name
            container_executable = Path("/workspace") / executable.name
            inner = shlex.split(
                template.format(src=str(container_source), exe=str(container_executable))
            )
            image = (
                os.getenv("OJ_PYTHON_IMAGE", "oj-python:3.10")
                if language.name == "python"
                else os.getenv("OJ_CPP_IMAGE", "oj-cpp:gcc13")
            )
            container_name = f"oj-{secrets.token_hex(8)}"
            args = [
                "docker",
                "run",
                "--rm",
                "--interactive",
                f"--name={container_name}",
                "--network=none",
                f"--memory={memory_limit}m",
                f"--memory-swap={memory_limit}m",
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
        return await self._execute(
            args,
            stdin,
            timeout,
            process_memory,
            directory,
            use_process_limit=not docker,
            docker_container=container_name,
        )

    async def _execute(
        self,
        args: list[str],
        stdin: str,
        timeout: float,
        memory_limit: int,
        cwd: Path,
        *,
        use_process_limit: bool = True,
        docker_container: str | None = None,
    ) -> ProcessResult:
        started = time.perf_counter()
        preexec_fn = self._memory_limiter(memory_limit) if use_process_limit else None
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                start_new_session=True,
                preexec_fn=preexec_fn,
            )
        except (OSError, ValueError) as exc:
            return ProcessResult("UNK", stderr=str(exc))

        monitor = asyncio.create_task(self._monitor_memory(process, memory_limit))
        communicate = asyncio.create_task(self._communicate_limited(process, stdin))
        timed_out = False
        try:
            stdout_bytes, stderr_bytes, output_exceeded = await asyncio.wait_for(
                asyncio.shield(communicate),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            timed_out = True
            if docker_container is not None:
                await self._kill_docker_container(docker_container)
            self._kill_process_tree(process)
            stdout_bytes, stderr_bytes, output_exceeded = await communicate
        except asyncio.CancelledError:
            if docker_container is not None:
                await asyncio.shield(self._kill_docker_container(docker_container))
            self._kill_process_tree(process)
            await asyncio.gather(communicate, monitor, return_exceptions=True)
            raise
        memory_mb, memory_exceeded = await monitor
        if docker_container is not None and (output_exceeded or memory_exceeded):
            await self._kill_docker_container(docker_container)
        await process.wait()
        if use_process_limit:
            # A program can fork, close its inherited pipes, and let its parent
            # exit successfully.  Always clear the isolated process group so
            # such descendants cannot outlive a local judging command.
            self._kill_process_tree(process)
        elapsed = time.perf_counter() - started
        if memory_exceeded:
            result: CaseResult = "MLE"
        elif timed_out:
            result = "TLE"
        elif output_exceeded:
            result = "UNK"
        elif process.returncode in {137, -signal.SIGKILL} and not use_process_limit:
            # Docker reports an OOM-killed container as SIGKILL/137.
            result = "MLE"
        elif process.returncode in {125, 126, 127} and not use_process_limit:
            # Docker CLI/image/entrypoint failures are judge infrastructure errors.
            result = "UNK"
        elif process.returncode != 0 and self._looks_like_memory_error(stderr_bytes):
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

    async def _communicate_limited(
        self,
        process: asyncio.subprocess.Process,
        stdin: str,
    ) -> tuple[bytes, bytes, bool]:
        async def feed_input() -> None:
            if process.stdin is None:
                return
            try:
                process.stdin.write(stdin.encode("utf-8"))
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                process.stdin.close()

        async def read_stream(
            stream: asyncio.StreamReader | None,
        ) -> tuple[bytes, bool]:
            if stream is None:
                return b"", False
            captured = bytearray()
            exceeded = False
            while chunk := await stream.read(64 * 1024):
                remaining = self.MAX_OUTPUT_BYTES - len(captured)
                if remaining > 0:
                    captured.extend(chunk[:remaining])
                if len(chunk) > remaining and not exceeded:
                    exceeded = True
                    self._kill_process_tree(process)
            return bytes(captured), exceeded

        _, stdout_result, stderr_result = await asyncio.gather(
            feed_input(),
            read_stream(process.stdout),
            read_stream(process.stderr),
        )
        stdout, stdout_exceeded = stdout_result
        stderr, stderr_exceeded = stderr_result
        return stdout, stderr, stdout_exceeded or stderr_exceeded

    @staticmethod
    def _memory_limiter(memory_limit: int):
        if resource is None or os.name != "posix":
            return None

        limit_bytes = memory_limit * 1024 * 1024

        def apply_limit() -> None:
            resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))

        return apply_limit

    @staticmethod
    def _looks_like_memory_error(stderr: bytes) -> bool:
        lowered = stderr.lower()
        return any(
            marker in lowered
            for marker in (
                b"memoryerror",
                b"std::bad_alloc",
                b"cannot allocate memory",
                b"out of memory",
            )
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

    @staticmethod
    async def _kill_docker_container(container_name: str) -> None:
        """Best-effort removal when the attached Docker client is interrupted."""
        try:
            cleanup = await asyncio.create_subprocess_exec(
                "docker",
                "kill",
                container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(cleanup.wait(), timeout=2)
        except (OSError, asyncio.TimeoutError):
            if "cleanup" in locals() and cleanup.returncode is None:
                cleanup.kill()
                await cleanup.wait()

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
        local_script = directory / "spj.py"
        input_path = directory / "spj-input.txt"
        expected_path = directory / "spj-expected.txt"
        actual_path = directory / "spj-actual.txt"
        await asyncio.gather(
            asyncio.to_thread(shutil.copyfile, script, local_script),
            asyncio.to_thread(input_path.write_text, testcase.input, encoding="utf-8"),
            asyncio.to_thread(expected_path.write_text, testcase.output, encoding="utf-8"),
            asyncio.to_thread(actual_path.write_text, actual, encoding="utf-8"),
        )
        language = Language(
            name="python",
            file_ext=".py",
            run_cmd="python3 {src} spj-input.txt spj-expected.txt spj-actual.txt",
            time_limit=2,
            memory_limit=64,
        )
        result = await self._run_command(
            language.run_cmd,
            local_script,
            directory / "unused",
            directory,
            "",
            2,
            64,
            language,
        )
        return "AC" if result.result == "AC" else "WA"

    @staticmethod
    def _normalize(value: str) -> str:
        lines = [line.rstrip() for line in value.replace("\r\n", "\n").split("\n")]
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

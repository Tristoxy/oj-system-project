"""Application paths and runtime configuration."""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
SESSION_COOKIE = "oj_session"
SESSION_TTL_SECONDS = 24 * 60 * 60
SUBMISSION_RATE_LIMIT = 3
SUBMISSION_RATE_WINDOW_SECONDS = 60
DEFAULT_TIME_LIMIT = 3.0
DEFAULT_MEMORY_LIMIT = 128


# 函数 `judge_backend`：负责当前模块中的对应操作。
def judge_backend() -> str:
    """Return auto, local, or docker according to the environment."""
    # 本地模式保证没有 Docker 的机器也能运行基础项目。
    # 如需启用进阶 Docker 判题，可显式设置 OJ_JUDGE_BACKEND=docker。
    value = os.getenv("OJ_JUDGE_BACKEND", "local").lower()
    return value if value in {"auto", "local", "docker"} else "auto"


# 函数 `secure_cookies`：负责当前模块中的对应操作。
def secure_cookies() -> bool:
    """Use Secure cookies when the deployment is served over HTTPS."""
    return os.getenv("OJ_SECURE_COOKIES", "false").lower() in {"1", "true", "yes"}

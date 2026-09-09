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


# 将环境变量 OJ_SECURE_COOKIES 解析为 Session Cookie 的 Secure 开关。
def secure_cookies() -> bool:
    """Use Secure cookies when the deployment is served over HTTPS."""
    return os.getenv("OJ_SECURE_COOKIES", "false").lower() in {"1", "true", "yes"}

"""Application paths and runtime configuration."""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
SESSION_COOKIE = "oj_session"
SESSION_TTL_SECONDS = 24 * 60 * 60
SUBMISSION_RATE_LIMIT = 3
SUBMISSION_RATE_WINDOW_SECONDS = 60


def judge_backend() -> str:
    """Return auto, local, or docker according to the environment."""
    value = os.getenv("OJ_JUDGE_BACKEND", "auto").lower()
    return value if value in {"auto", "local", "docker"} else "auto"

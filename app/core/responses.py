"""Helpers for building the response format required by the course API."""

from typing import Any


def success_response(data: Any = None, msg: str = "success") -> dict[str, Any]:
    return {"code": 200, "msg": msg, "data": data}

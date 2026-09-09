"""Helpers for building the response format required by the course API."""

from typing import Any


# 函数 `success_response`：负责当前模块中的对应操作。
def success_response(data: Any = None, msg: str = "success") -> dict[str, Any]:
    return {"code": 200, "msg": msg, "data": data}

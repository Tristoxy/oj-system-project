"""Helpers for building the response format required by the course API."""

from typing import Any

# api成功响应
# 按课程 API 约定包装所有成功响应的 code/msg/data 三个字段。
def success_response(data: Any = None, msg: str = "success") -> dict[str, Any]:
    return {"code": 200, "msg": msg, "data": data}

"""Audit-log models."""

from pydantic import BaseModel, ConfigDict

# 用户访问记录，谁、哪道题、什么操作、什么时候、状态码
class AccessLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    problem_id: str
    action: str = "view_logs"
    time: str
    status: str

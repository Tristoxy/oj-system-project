"""Audit-log models."""

from pydantic import BaseModel


class AccessLog(BaseModel):
    user_id: str
    problem_id: str
    action: str = "view_logs"
    time: str
    status: str

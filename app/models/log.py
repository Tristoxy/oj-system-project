"""Audit-log models."""

from pydantic import BaseModel, ConfigDict


class AccessLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    problem_id: str
    action: str = "view_logs"
    time: str
    status: str

"""Plagiarism-analysis task models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlagiarismRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id: str = Field(min_length=1)
    threshold: float = Field(default=0.8, ge=0, le=1)


class PlagiarismMatch(BaseModel):
    left_submission_id: str
    right_submission_id: str
    similarity: float
    is_clone: bool


class PlagiarismTask(BaseModel):
    task_id: str
    problem_id: str
    threshold: float
    status: Literal["pending", "success", "error"] = "pending"
    matches: list[PlagiarismMatch] = Field(default_factory=list)
    created_at: str

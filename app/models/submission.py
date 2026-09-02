"""Submission and per-test-case result models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SubmissionStatus = Literal["pending", "success", "error"]
CaseResult = Literal["AC", "WA", "TLE", "MLE", "RE", "CE", "UNK"]


class SubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    code: str = Field(min_length=1, max_length=200_000)


class TestCaseResult(BaseModel):
    id: int
    result: CaseResult
    time: float
    memory: float


class Submission(BaseModel):
    submission_id: str
    user_id: str
    problem_id: str
    language: str
    code: str
    status: SubmissionStatus = "pending"
    details: list[TestCaseResult] = Field(default_factory=list)
    score: int = 0
    counts: int = 0
    created_at: str
    pdg: dict[str, object] | None = None

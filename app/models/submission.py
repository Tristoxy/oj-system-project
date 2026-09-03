"""Submission and per-test-case result models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SubmissionStatus = Literal["pending", "success", "error"]
CaseResult = Literal["AC", "WA", "TLE", "MLE", "RE", "CE", "UNK"]
IMPORTED_SUBMISSION_TIME = "1970-01-01T00:00:00+00:00"


class SubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    code: str = Field(min_length=1, max_length=200_000)


class TestCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1)
    result: CaseResult
    time: float = Field(ge=0)
    memory: float = Field(ge=0)


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    problem_id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    code: str = Field(min_length=1, max_length=200_000)
    status: SubmissionStatus = "pending"
    details: list[TestCaseResult] = Field(default_factory=list)
    score: int = Field(default=0, ge=0)
    counts: int = Field(default=0, ge=0)
    # The course's fixed import/export schema predates this internal field.  An
    # imported submission without a timestamp must not count towards the
    # one-minute rate limit, so use an old, timezone-aware default.
    created_at: str = IMPORTED_SUBMISSION_TIME
    pdg: dict[str, object] | None = None

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        datetime.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def validate_result_totals(self) -> "Submission":
        if self.score > self.counts:
            raise ValueError("score cannot exceed counts")
        case_ids = [detail.id for detail in self.details]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("test case result ids must be unique")
        return self

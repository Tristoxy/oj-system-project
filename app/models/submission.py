"""Submission and per-test-case result models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.language import Language
from app.models.problem import Problem


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


class JudgeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem: Problem
    language: Language


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
    compile_info: dict[str, str] | None = None
    run_info: dict[str, str] | None = None
    error_info: str = ""
    # 课程固定导入导出结构早于此内部字段；缺少时间戳的导入记录不应计入一分钟限流，
    # 因此使用一个较早且带时区的默认时间。
    created_at: str = IMPORTED_SUBMISSION_TIME
    pdg: dict[str, object] | None = None
    judge_snapshot: JudgeSnapshot | None = None

    # 确保提交时间是可解析且包含时区的 ISO 时间，避免限流比较混用本地时间。
    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    # counts 表示测例个数、每个测例 10 分；同时确保测例编号没有重复。
    @model_validator(mode="after")
    def validate_result_totals(self) -> "Submission":
        if self.score > self.counts * 10:
            raise ValueError("score cannot exceed counts * 10")
        case_ids = [detail.id for detail in self.details]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("test case result ids must be unique")
        return self

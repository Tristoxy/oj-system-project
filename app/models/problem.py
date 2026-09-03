"""Pydantic models describing an OJ problem."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PROBLEM_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str
    output: str


class ProblemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=PROBLEM_ID_PATTERN)
    title: str = Field(min_length=1)
    description: str
    input_description: str
    output_description: str
    samples: list[TestCase]
    constraints: str
    testcases: list[TestCase]
    hint: str = ""
    source: str = ""
    tags: list[str] = Field(default_factory=list)
    time_limit: float | None = Field(default=None, gt=0, le=60)
    memory_limit: int | None = Field(default=None, gt=0, le=4096)
    author: str = ""
    difficulty: str = ""
    public_cases: bool = False
    judge_mode: Literal["standard", "strict", "spj"] = "standard"


class Problem(ProblemCreate):
    """Stored problem model; currently identical to the creation payload."""


class ProblemUpdate(BaseModel):
    """Partial problem edit; dedicated admin-only settings are intentionally absent."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, min_length=1, pattern=PROBLEM_ID_PATTERN)
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    input_description: str | None = None
    output_description: str | None = None
    samples: list[TestCase] | None = None
    constraints: str | None = None
    testcases: list[TestCase] | None = None
    hint: str | None = None
    source: str | None = None
    tags: list[str] | None = None
    time_limit: float | None = Field(default=None, gt=0, le=60)
    memory_limit: int | None = Field(default=None, gt=0, le=4096)
    author: str | None = None
    difficulty: str | None = None

    @model_validator(mode="after")
    def require_edit(self) -> "ProblemUpdate":
        if not self.model_fields_set or self.model_fields_set == {"id"}:
            raise ValueError("at least one problem field must be updated")
        return self

"""Pydantic models describing an OJ problem."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    time_limit: float = Field(default=3.0, gt=0, le=60)
    memory_limit: int = Field(default=128, gt=0, le=4096)
    author: str = ""
    difficulty: str = ""
    public_cases: bool = False
    judge_mode: Literal["standard", "strict", "spj"] = "standard"


class Problem(ProblemCreate):
    """Stored problem model; currently identical to the creation payload."""

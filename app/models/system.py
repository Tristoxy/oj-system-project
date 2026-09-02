"""Validated import/export structure."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.problem import Problem
from app.models.submission import Submission
from app.models.user import User


class ImportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    users: list[User] = Field(default_factory=list)
    problems: list[Problem] = Field(default_factory=list)
    submissions: list[Submission] = Field(default_factory=list)

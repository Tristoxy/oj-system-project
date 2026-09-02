"""User, authentication, and role models."""

from typing import Literal

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


Role = Literal["user", "admin", "banned"]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=6)


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role


class User(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=1)
    role: Role = "user"
    join_time: str
    submit_count: int = Field(default=0, ge=0)
    resolve_count: int = Field(default=0, ge=0)

    @field_validator("join_time")
    @classmethod
    def validate_join_date(cls, value: str) -> str:
        datetime.strptime(value, "%Y-%m-%d")
        return value

    def public(self) -> dict[str, object]:
        return self.model_dump(exclude={"password"})


class Session(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    user_id: str
    expires_at: float

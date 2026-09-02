"""User, authentication, and role models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Role = Literal["user", "admin", "banned"]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=6)


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role


class User(BaseModel):
    user_id: str
    username: str
    password: str
    role: Role = "user"
    join_time: str
    submit_count: int = 0
    resolve_count: int = 0

    def public(self) -> dict[str, object]:
        return self.model_dump(exclude={"password"})


class Session(BaseModel):
    session_id: str
    user_id: str
    expires_at: float

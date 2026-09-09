"""Models used by the optional AI-assisted problem authoring module."""

from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


AITaskStatus = Literal["pending", "running", "success", "cancelled", "error"]


class ModelConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=200)
    api_key: str = Field(min_length=1, max_length=4096)
    input_price: float = Field(default=0, ge=0)
    output_price: float = Field(default=0, ge=0)
    price_unit: int = Field(default=1_000_000, gt=0)

    # 去除地址末尾斜杠，并拒绝缺少 http(s) 协议或主机名的模型服务地址。
    @field_validator("provider_url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("provider_url must be an http(s) URL")
        return normalized


class ProblemTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(min_length=3, max_length=20_000)
    problem_id: str | None = Field(default=None, min_length=1, max_length=200)


class AIUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost: float = Field(default=0, ge=0)
    currency: str = "USD"


class AIProblemTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    user_id: str
    status: AITaskStatus = "pending"
    progress: str = "等待开始"
    result: dict[str, Any] | None = None
    usage: AIUsage = Field(default_factory=AIUsage)
    error: str = ""

"""Dynamic judge-language configuration."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LanguageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_+-]+$")
    file_ext: str = Field(min_length=1, max_length=16)
    compile_cmd: str | None = Field(default=None, max_length=500)
    run_cmd: str = Field(min_length=1, max_length=500)
    time_limit: float = Field(default=3.0, gt=0, le=60)
    memory_limit: int = Field(default=128, gt=0, le=4096)

    @field_validator("file_ext")
    @classmethod
    def normalize_extension(cls, value: str) -> str:
        if any(character in value for character in ("/", "\\", "\x00")):
            raise ValueError("invalid file extension")
        return value if value.startswith(".") else f".{value}"


class Language(LanguageCreate):
    pass

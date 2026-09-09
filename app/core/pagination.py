"""Shared pagination validation."""

from typing import TypeVar

from app.core.exceptions import ApiError


T = TypeVar("T")


# 函数 `paginate`：负责当前模块中的对应操作。
def paginate(items: list[T], page: int | None, page_size: int | None) -> list[T]:
    if page is not None and page_size is None:
        raise ApiError(400, "page_size is required when page is provided")
    if page is not None and page < 1 or page_size is not None and page_size < 1:
        raise ApiError(400, "page and page_size must be positive")
    if page is None and page_size is None:
        return items
    effective_page = page or 1
    assert page_size is not None
    start = (effective_page - 1) * page_size
    return items[start : start + page_size]

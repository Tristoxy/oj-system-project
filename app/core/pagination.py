"""Shared pagination validation."""

from typing import TypeVar

from app.core.exceptions import ApiError


T = TypeVar("T")

# 处理分页
# 校验 page/page_size 必须成对且为正数，再切出对应的一页数据。
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

"""Evaluation log and audit endpoints."""

from fastapi import APIRouter, Depends, Query

from app.container import AppContainer
from app.core.responses import success_response
from app.dependencies import get_container, get_current_user, require_admin
from app.models.user import User


router = APIRouter(tags=["logs"])


# 函数 `get_submission_log`：负责当前模块中的对应操作。
@router.get("/api/submissions/{submission_id}/log")
async def get_submission_log(
    submission_id: str,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return success_response(await container.logs.get_log(submission_id, current_user))


# 函数 `list_access_logs`：负责当前模块中的对应操作。
@router.get("/api/logs/access/")
async def list_access_logs(
    user_id: str | None = Query(default=None),
    problem_id: str | None = Query(default=None),
    page: int | None = Query(default=None),
    page_size: int | None = Query(default=None),
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    return success_response(
        await container.logs.list_access_logs(user_id, problem_id, page, page_size)
    )

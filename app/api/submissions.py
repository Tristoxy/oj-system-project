"""Submission, result, listing, and rejudge endpoints."""

from fastapi import APIRouter, Depends, Query

from app.container import AppContainer
from app.core.responses import success_response
from app.dependencies import get_container, get_current_user, require_admin
from app.models.submission import SubmissionCreate
from app.models.user import User


router = APIRouter(prefix="/api/submissions", tags=["submissions"])

# 校验用户信息后，提交任务并返回提交id
# 为当前用户创建 pending 提交并启动异步评测，接口不等待判题完成。
@router.post("/")
async def submit_code(
    payload: SubmissionCreate,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    submission = await container.submissions.submit(payload, current_user)
    return success_response(
        {"submission_id": submission.submission_id, "status": submission.status}
    )


# 按用户、题目、任务状态和分页参数查询当前用户有权查看的提交摘要。
@router.get("/")
async def list_submissions(
    user_id: str | None = Query(default=None),
    problem_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int | None = Query(default=None),
    page_size: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    data = await container.submissions.list_submissions(
        current_user,
        user_id,
        problem_id,
        status,
        page,
        page_size,
    )
    return success_response(data)


# 返回本人或管理员可见的单次提交状态、分数及编译运行信息。
@router.get("/{submission_id}")
async def get_submission(
    submission_id: str,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return success_response(
        await container.submissions.result_for(submission_id, current_user)
    )


# 仅管理员可把指定提交重置为 pending，并重新加入后台评测队列。
@router.put("/{submission_id}/rejudge")
async def rejudge_submission(
    submission_id: str,
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    submission = await container.submissions.rejudge(submission_id)
    return success_response(
        {"submission_id": submission.submission_id, "status": "pending"},
        msg="rejudge started",
    )

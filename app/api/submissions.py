"""Submission, result, listing, and rejudge endpoints."""

from fastapi import APIRouter, Depends, Query

from app.container import AppContainer
from app.core.responses import success_response
from app.dependencies import get_container, get_current_user, require_admin
from app.models.submission import SubmissionCreate
from app.models.user import User


router = APIRouter(prefix="/api/submissions", tags=["submissions"])


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


@router.get("/{submission_id}")
async def get_submission(
    submission_id: str,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return success_response(
        await container.submissions.result_for(submission_id, current_user)
    )


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

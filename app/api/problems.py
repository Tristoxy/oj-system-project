"""Problem-management HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.container import AppContainer
from app.core.responses import success_response
from app.dependencies import get_container, get_current_user, require_admin
from app.models.problem import PROBLEM_ID_PATTERN, ProblemCreate
from app.models.user import User


router = APIRouter(prefix="/api/problems", tags=["problems"])


class VisibilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    public_cases: bool = False


@router.get("/")
async def list_problems(
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del current_user
    problems = await container.problems.list_problems()
    return success_response(problems)


@router.post("/", status_code=status.HTTP_200_OK)
async def add_problem(
    problem: ProblemCreate,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del current_user
    created = await container.problems.add_problem(problem)
    return success_response({"id": created.id}, msg="add success")


@router.get("/{problem_id}")
async def get_problem(
    problem_id: Annotated[str, Path(min_length=1, pattern=PROBLEM_ID_PATTERN)],
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del current_user
    problem = await container.problems.get_problem(problem_id)
    return success_response(problem.model_dump(mode="json"))


@router.delete("/{problem_id}")
async def delete_problem(
    problem_id: Annotated[str, Path(min_length=1, pattern=PROBLEM_ID_PATTERN)],
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    await container.problems.delete_problem(problem_id)
    return success_response({"id": problem_id}, msg="delete success")


@router.put("/{problem_id}/log_visibility")
async def update_log_visibility(
    problem_id: Annotated[str, Path(min_length=1, pattern=PROBLEM_ID_PATTERN)],
    payload: VisibilityUpdate,
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    problem = await container.problems.set_log_visibility(problem_id, payload.public_cases)
    return success_response(
        {"problem_id": problem.id, "public_cases": problem.public_cases},
        msg="log visibility updated",
    )


@router.post("/{problem_id}/spj")
async def upload_spj(
    problem_id: Annotated[str, Path(min_length=1, pattern=PROBLEM_ID_PATTERN)],
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    content = await file.read()
    await container.problems.save_spj(problem_id, file.filename or "", content)
    return success_response({"problem_id": problem_id}, msg="SPJ uploaded")


@router.delete("/{problem_id}/spj")
async def delete_spj(
    problem_id: Annotated[str, Path(min_length=1, pattern=PROBLEM_ID_PATTERN)],
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    await container.problems.delete_spj(problem_id)
    return success_response({"problem_id": problem_id}, msg="SPJ deleted")

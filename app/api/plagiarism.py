"""Administrator-only plagiarism task endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.container import AppContainer
from app.core.responses import success_response
from app.dependencies import get_container, require_admin
from app.models.plagiarism import PlagiarismRequest
from app.models.user import User


router = APIRouter(prefix="/api/plagiarism", tags=["plagiarism"])


# 函数 `start_plagiarism_check`：负责当前模块中的对应操作。
@router.post("/")
async def start_plagiarism_check(
    payload: PlagiarismRequest,
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    task = await container.plagiarism.start(payload)
    return success_response({"task_id": task.task_id, "status": task.status})


# 函数 `get_plagiarism_result`：负责当前模块中的对应操作。
@router.get("/{task_id}")
async def get_plagiarism_result(
    task_id: str,
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    task = await container.plagiarism.get(task_id)
    return success_response(task.model_dump(mode="json"))


# 函数 `download_plagiarism_report`：负责当前模块中的对应操作。
@router.get("/{task_id}/report")
async def download_plagiarism_report(
    task_id: str,
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> FileResponse:
    del admin
    path = await container.plagiarism.report_path(task_id)
    return FileResponse(path, media_type="application/json", filename=path.name)

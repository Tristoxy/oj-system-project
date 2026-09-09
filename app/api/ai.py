"""AI-assisted problem authoring endpoints."""

from fastapi import APIRouter, Depends

from app.container import AppContainer
from app.core.responses import success_response
from app.dependencies import get_container, get_current_user
from app.models.ai import ModelConfigUpdate, ProblemTaskCreate
from app.models.user import User


router = APIRouter(prefix="/api/ai", tags=["ai-problem-authoring"])


# 函数 `update_model_config`：负责当前模块中的对应操作。
@router.put("/model-config")
async def update_model_config(
    payload: ModelConfigUpdate,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    data = await container.ai.set_config(current_user, payload)
    return success_response(data, msg="model config updated")


# 函数 `get_model_config`：负责当前模块中的对应操作。
@router.get("/model-config")
async def get_model_config(
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return success_response(await container.ai.get_config(current_user))


# 函数 `create_problem_task`：负责当前模块中的对应操作。
@router.post("/problem-tasks/")
async def create_problem_task(
    payload: ProblemTaskCreate,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    task = await container.ai.create(payload, current_user)
    return success_response(
        {"task_id": task.task_id, "status": task.status}, msg="task created"
    )


# 函数 `get_problem_task`：负责当前模块中的对应操作。
@router.get("/problem-tasks/{task_id}")
async def get_problem_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    task = await container.ai.get(task_id, current_user)
    return success_response(task.model_dump(mode="json", exclude={"user_id"}))


# 函数 `cancel_problem_task`：负责当前模块中的对应操作。
@router.put("/problem-tasks/{task_id}/cancel")
async def cancel_problem_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    task = await container.ai.cancel(task_id, current_user)
    return success_response(
        {"task_id": task.task_id, "status": task.status}, msg="task cancelled"
    )

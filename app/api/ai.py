"""AI-assisted problem authoring endpoints."""

from fastapi import APIRouter, Depends

from app.container import AppContainer
from app.core.responses import success_response
from app.dependencies import get_container, get_current_user
from app.models.ai import ModelConfigUpdate, ProblemTaskCreate
from app.models.user import User


router = APIRouter(prefix="/api/ai", tags=["ai-problem-authoring"])


# 保存当前用户本次进程内的模型地址、名称、密钥和计价配置。
@router.put("/model-config")
async def update_model_config(
    payload: ModelConfigUpdate,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    data = await container.ai.set_config(current_user, payload)
    return success_response(data, msg="model config updated")


# 返回当前用户的非敏感模型配置，绝不回传 API Key 原文。
@router.get("/model-config")
async def get_model_config(
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return success_response(await container.ai.get_config(current_user))


# 创建异步 AI 命题任务，并立即返回可供前端轮询的任务编号和状态。
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


# 查询本人或管理员可见的 AI 命题进度、结果和 Token 用量。
@router.get("/problem-tasks/{task_id}")
async def get_problem_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    task = await container.ai.get(task_id, current_user)
    return success_response(task.model_dump(mode="json", exclude={"user_id"}))


# 中断本人或管理员有权操作且尚未结束的 AI 命题任务。
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

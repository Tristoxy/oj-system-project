"""Problem-management HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.container import AppContainer
from app.core.responses import success_response
from app.dependencies import get_container, get_current_user, require_admin
from app.models.problem import PROBLEM_ID_PATTERN, ProblemCreate, ProblemUpdate
from app.models.user import User


router = APIRouter(prefix="/api/problems", tags=["problems"])


class VisibilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    public_cases: bool = False

# 题目列表及题目简要信息
# 返回题号和标题组成的题库索引，供检索和选择题目使用。
@router.get("/")
async def list_problems(
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del current_user
    problems = await container.problems.list_problems()
    return success_response(problems)

# 新增题目
# 接收并校验完整题目配置，创建题目并返回其唯一题号。
@router.post("/", status_code=status.HTTP_200_OK)
async def add_problem(
    problem: ProblemCreate,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del current_user
    created = await container.problems.add_problem(problem)
    return success_response({"id": created.id}, msg="add success")

# 查询题目
# 按路径中的题号返回题面、样例、限制、测例和可选字段。
@router.get("/{problem_id}")
async def get_problem(
    problem_id: Annotated[str, Path(min_length=1, pattern=PROBLEM_ID_PATTERN)],
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del current_user
    problem = await container.problems.get_problem(problem_id)
    return success_response(problem.model_dump(mode="json"))

# 修改题目 更新
# 将请求中的部分字段合并进指定题目；题号本身不允许改变。
@router.put("/{problem_id}")
async def update_problem(
    problem_id: Annotated[str, Path(min_length=1, pattern=PROBLEM_ID_PATTERN)],
    payload: ProblemUpdate,
    current_user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del current_user
    problem = await container.problems.update_problem(problem_id, payload)
    return success_response({"id": problem.id}, msg="update success")


# 仅管理员可删除指定题目，并由服务层同时清理其 SPJ 脚本。
@router.delete("/{problem_id}")
async def delete_problem(
    problem_id: Annotated[str, Path(min_length=1, pattern=PROBLEM_ID_PATTERN)],
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    await container.problems.delete_problem(problem_id)
    return success_response({"id": problem_id}, msg="delete success")


# 仅管理员可切换题目测例日志是否向所有登录用户公开。
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

# 管理员上传spj
# 仅管理员可上传至多 256 KB 的 Python SPJ 文件并启用 SPJ 模式。
@router.post("/{problem_id}/spj")
async def upload_spj(
    problem_id: Annotated[str, Path(min_length=1, pattern=PROBLEM_ID_PATTERN)],
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    content = await file.read(256_001)
    await container.problems.save_spj(problem_id, file.filename or "", content)
    return success_response({"problem_id": problem_id}, msg="SPJ uploaded")


# 仅管理员可删除题目的 SPJ 文件，并恢复标准输出比较模式。
@router.delete("/{problem_id}/spj")
async def delete_spj(
    problem_id: Annotated[str, Path(min_length=1, pattern=PROBLEM_ID_PATTERN)],
    admin: User = Depends(require_admin),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    del admin
    await container.problems.delete_spj(problem_id)
    return success_response({"problem_id": problem_id}, msg="SPJ deleted")

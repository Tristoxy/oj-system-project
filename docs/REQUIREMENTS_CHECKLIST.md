# 课程要求对照表

| 要求 | 实现位置 | 自动验证 |
| --- | --- | --- |
| 全部 API 使用 `async def` | `app/api/` | `tests/test_async_routes.py` |
| HTTP 状态码与 JSON `code` 一致 | `app/core/exceptions.py` | `tests/test_api_contract.py` |
| 401 > 403 > 400 > 429 > 409 > 404 | 路由依赖、服务检查顺序 | API/用户/评测测试 |
| 题目字段校验和默认值 | `models/problem.py` | `test_problems.py` |
| 题目增、删、查、列表 | `api/problems.py`、`services/problem_service.py` | `test_problems.py` |
| Python/C++ 评测 | `judge/runner.py` | `test_judge.py` |
| AC/WA/RE/CE/TLE/MLE/UNK | `judge/runner.py` | `test_judge.py` |
| 行末空格/末尾换行归一化 | `JudgeRunner._normalize` | `test_judge.py` |
| 动态注册及查询语言 | `language_service.py` | `test_api_contract.py` |
| 提交立即返回 pending | `submission_service.py` | `test_judge.py` |
| 查询、筛选、分页、重判 | `submission_service.py` | `test_judge.py` |
| 初始管理员、注册、登录、登出 | `auth_service.py`、`user_service.py` | `test_users.py` |
| 密码加盐哈希 | `core/security.py` | `test_system.py` |
| user/admin/banned 权限 | `dependencies.py` | `test_users.py`、`test_logs.py` |
| 一分钟最多三次提交 | `submission_service.py` | `test_judge.py` |
| 用户提交数和通过题数 | `state_helpers.py` | `test_judge.py` |
| 测例日志及内容裁剪 | `log_service.py` | `test_logs.py` |
| 日志可见性和访问审计 | `log_service.py` | `test_logs.py` |
| 重启持久化及 pending 恢复 | `state_store.py`、`container.py` | `test_persistence.py` |
| reset 恢复初始管理员 | `system_service.py` | `test_system.py` |
| 固定 JSON 导入导出、冲突覆盖 | `system_service.py` | `test_system.py` |
| Adv1 Special Judge | `problem_service.py`、`judge/runner.py` | `test_spj.py` |
| Adv2 Streamlit 前端 | `frontend/app.py` | Python 语法检查、人工演示 |
| Adv3 Docker 强制隔离模式 | `docker/`、`judge/runner.py` | `test_docker_sandbox.py`；需本机实测 |
| Adv4 AST/CFG/PDG 查重 | `plagiarism/`、`plagiarism_service.py` | `test_plagiarism.py` |
| Conventional Commits | Git 历史 | `git log --oneline` |
| 避免提交大文件/运行数据 | `.gitignore`、`.dockerignore` | `git count-objects -vH` |

## 提交前人工检查

1. 在课程 Linux/WSL 环境执行 `python -m pytest -q`。
2. 有 Docker 时构建评测镜像，以 `OJ_JUDGE_BACKEND=docker` 手动提交 Python/C++ 的
   AC、TLE 和 MLE 程序。
3. 启动 Streamlit，演示注册、登录、题目、提交、轮询结果和历史记录。
4. 把 `docs/COURSE_REPORT.md` 中的个人信息和 AI 使用比例替换为实际情况，并加入演示截图。
5. 确认 `git status` 干净，仓库中没有 `data/`、`.venv/`、压缩包或镜像文件。

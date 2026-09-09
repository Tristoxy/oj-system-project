# 课程要求对照表

| 要求 | 实现位置 | 自动验证 |
| --- | --- | --- |
| 全部 API 使用 `async def` | `app/api/` | `tests/test_async_routes.py` |
| HTTP 状态码与 JSON `code` 一致 | `app/core/exceptions.py` | `tests/test_api_contract.py` |
| 401 > 403 > 400 > 429 > 409 > 404 | 路由依赖、服务检查顺序 | API/用户/评测测试 |
| 题目字段校验、默认值和可选资源限制 | `models/problem.py` | `test_problems.py` |
| 题目增、删、查、列表和登录用户修改 | `api/problems.py`、`services/problem_service.py` | `test_problems.py`、`test_course_contract.py` |
| 普通用户查看完整 testcases | `api/problems.py` | `test_course_contract.py` |
| Python/C++ 评测 | `judge/runner.py` | `test_judge.py` |
| AC/WA/RE/CE/TLE/MLE/UNK | `judge/runner.py` | `test_judge.py` |
| 题目→语言→系统的逐字段限制优先级 | `judge/runner.py`、`core/config.py` | `test_judge.py` |
| 行末空格/末尾换行归一化 | `JudgeRunner._normalize` | `test_judge.py` |
| 动态注册、查询及实际运行语言 | `language_service.py` | `test_judge.py` |
| 提交立即返回 pending | `submission_service.py` | `test_judge.py` |
| 提交配置快照、改题不隐式重评 | `submission_service.py` | `test_judge.py` |
| 查询、筛选、分页、重判 | `submission_service.py` | `test_judge.py` |
| 评测详情含编译、运行和任务错误信息 | `models/submission.py`、`submission_service.py` | `test_judge.py` |
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
| 官方 submission 格式兼容 | `models/submission.py` | `test_system.py` |
| 导入后完整恢复后台任务 | `api/system.py` | `test_system.py` |
| Step 6 完整 Streamlit 页面组 | `frontend/app.py` | Python 语法检查、人工演示 |
| AI R1 出题界面及审阅入库 | `frontend/app.py`、`api/ai.py` | `test_ai.py`、人工演示 |
| AI R2 自定义模型配置且密钥不落盘/不回传 | `models/ai.py`、`ai_service.py` | `test_ai.py` |
| AI R3 每秒进度刷新与真实任务中断 | `frontend/app.py`、`ai_service.py` | `test_ai.py`、人工演示 |
| AI R4 Token 与费用统计 | `ai_service.py`、`frontend/app.py` | `test_ai.py` |
| 额外：Special Judge | `problem_service.py`、`judge/runner.py` | `test_spj.py` |
| 额外：AST→CFG→PDG 查重 | `plagiarism/`、`plagiarism_service.py` | 分支/汇合/循环/数据依赖测试 |
| HTTP 黑盒权限矩阵 | `app/api/`、`dependencies.py` | `test_course_contract.py` |
| Conventional Commits | Git 历史 | `git log --oneline` |
| 避免提交大文件/运行数据 | `.gitignore` | `git count-objects -vH` |

## 提交前人工检查

1. Windows 可用于日常开发；提交前建议在 WSL 或其他 Linux 环境执行 `python -m pytest -q`，确认兼容课程 Linux 自动评测。
2. 启动 Streamlit，演示注册、登录、用户管理、题目增删改查、提交、详情和日志。
3. 使用本人可用的 OpenAI 兼容模型完成一次 AI 命题，展示实时进度、Token/费用、结果入库；
   再启动一次慢任务并现场中断。
4. 把 `docs/COURSE_REPORT.md` 中的个人信息和 AI 使用比例替换为实际情况，并加入演示截图。
5. 确认 `git status` 干净，仓库中没有 `data/`、`.venv/`、压缩包或生成文件。

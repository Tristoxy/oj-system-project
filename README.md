# Python Course OJ

一个面向课程验收的异步 Online Judge。基础模块覆盖题目管理、Python/C++ 评测、评测
列表、用户与权限、日志审计和 Streamlit 前端；进阶模块实现 AI 智能命题 R1–R4，另外
保留 Special Judge、Docker 沙箱和 PDG 查重。

## 1. Windows CMD 快速运行

在项目根目录 `D:\Desktop\oj-system` 打开 CMD：

```cmd
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements-dev.txt
python -m pip install -r requirements-frontend.txt
```

启动后端（第一个 CMD）：

```cmd
.venv\Scripts\activate.bat
uvicorn app.main:app --reload
```

启动前端（第二个 CMD）：

```cmd
.venv\Scripts\activate.bat
streamlit run frontend\app.py
```

- 后端健康检查：<http://127.0.0.1:8000/health>
- Swagger：<http://127.0.0.1:8000/docs>
- 初始管理员：`admin` / `admintestpassword`
- 数据目录：`data/`（已忽略，不应提交）

## 2. 项目架构

```text
app/
├── main.py                 应用工厂、生命周期和路由注册
├── container.py            统一组装所有 Service
├── api/                    HTTP 路由：鉴权、参数接收、统一响应
├── core/                   配置、异常、分页、响应和命令安全
├── models/                 Pydantic 请求模型、持久化模型和校验器
├── services/               业务规则、权限后的数据操作和后台任务
├── judge/runner.py         本地/Docker 编译执行、限时限内存和输出比较
├── plagiarism/pdg.py       AST/CFG/PDG 查重和相似节点映射
└── repositories/state_store.py
                            加锁、深拷贝和原子 JSON 持久化
frontend/app.py             Streamlit 用户、题目、评测和 AI 页面
docker/                     Python/C++ 判题镜像定义
scripts/build_judge_images.sh
                            构建两个判题镜像的 Linux shell 脚本
tests/                      接口、评测、权限、持久化和 AI 回归测试
docs/                       要求对照、报告、安全说明和答辩材料
```

请求链路固定为：`HTTP → api 路由 → dependencies 鉴权 → service 业务逻辑 → StateStore`
；评测和 AI 命题在 service 中创建后台 asyncio 任务，分别调用受限进程或外部模型。

## 3. 文件和函数职责

下面列出实现文件中的每个函数；函数定义处也有同名注释，便于在编辑器中直接阅读。

### 3.1 应用入口和路由（`app/main.py`、`app/container.py`）

- `app/main.py`：`create_app` 创建 FastAPI、注册异常处理器和全部路由；内部 `lifespan`
  负责启动初始化和关闭后台任务。
- `app/container.py`：`AppContainer.__init__` 创建 Store、Runner 和各 Service；`initialize`
  初始化默认管理员/语言并恢复 pending 任务；`cancel_background_tasks` 取消评测、查重和
  AI 任务；`close` 在应用退出时完成清理。

### 3.2 API 路由（`app/api/`）

- `auth.py`：`login` 校验凭据并设置 Session Cookie；`logout` 删除服务端 Session。
- `health.py`：`health_check` 返回服务健康状态。
- `users.py`：`register_user` 注册普通用户；`create_admin` 创建管理员；`list_users` 分页
  列出用户；`get_user` 查询本人或管理员可见的信息；`update_role` 修改 user/admin/banned
  角色。
- `problems.py`：`list_problems` 列出题目摘要；`add_problem` 新增题目；`get_problem`
  返回完整题面和测试点；`update_problem` 修改题面；`delete_problem` 删除题目；
  `update_log_visibility` 设置测试点日志公开性；`upload_spj` 上传安全 SPJ；`delete_spj`
  删除 SPJ 并恢复标准判题。`VisibilityUpdate` 是日志公开设置模型。
- `languages.py`：`list_languages` 查询已注册语言；`register_language` 校验并注册语言。
- `submissions.py`：`submit_code` 创建 pending 评测；`list_submissions` 按题目/用户/状态
  筛选并分页；`get_submission` 查询任务状态、分数和编译/运行信息；`rejudge_submission`
  让管理员以原 ID 重新评测。
- `logs.py`：`get_submission_log` 返回按权限裁剪的测例详情；`list_access_logs` 返回管理员
  可见的日志访问审计。
- `system.py`：`reset_system` 清空并恢复初始系统；`export_data` 导出课程固定 JSON；
  `import_data` 校验并原子合并 JSON。
- `plagiarism.py`：`start_plagiarism_check` 创建查重任务；`get_plagiarism_result` 查询结果；
  `download_plagiarism_report` 下载管理员报告。
- `ai.py`：`update_model_config` 设置用户模型 URL/模型/密钥/价格；`get_model_config` 只返
  回是否配置密钥；`create_problem_task` 创建 AI 命题任务；`get_problem_task` 查询进度、
  结果和用量；`cancel_problem_task` 真实取消创建者或管理员的任务。

### 3.3 核心基础设施（`app/core/`、`app/dependencies.py`）

- `config.py`：`judge_backend` 读取 local/auto/docker 模式；`secure_cookies` 读取 HTTPS
  Secure Cookie 开关。
- `exceptions.py`：`ApiError.__init__` 保存业务错误；`error_content` 生成统一错误 JSON；
  `register_exception_handlers` 注册 400/401/403/404/500 等异常处理器，其中内部处理函数
  `handle_api_error`、`handle_validation_error`、`handle_http_error`、
  `handle_unexpected_error` 保证 HTTP 状态码与 `code` 一致。
- `pagination.py`：`paginate` 校验 page/page_size 并切出分页结果。
- `responses.py`：`success_response` 生成统一成功 JSON。
- `security.py`：`hash_password` 生成带随机盐的 PBKDF2 哈希；`verify_password` 校验密码；
  `is_password_hash` 验证导入哈希格式；`validate_command_template` 检查语言命令占位符、
  可执行程序白名单和危险 shell 字符。
- `dependencies.py`：`get_container` 取得当前应用容器；`get_current_user` 从 Cookie 解析
  登录用户；`require_admin` 在路由前完成管理员权限检查。

### 3.4 持久化仓库（`app/repositories/state_store.py`）

`empty_state` 创建空的 users/problems/languages/submissions 等集合；`StateStore.__init__`
配置数据、SPJ 和报告目录；`initialize/read/mutate/replace/clear_files` 是异步公共读写
接口；`_initialize_sync` 创建目录和初始 JSON；`_load_unlocked` 读取并补齐集合；
`_write_unlocked` 用临时文件原子替换；`_read_sync`、`_mutate_sync`、`_replace_sync`、
`_clear_files_sync` 分别完成加锁后的同步读、改、替换和文件清理。

### 3.5 数据模型（`app/models/`）

- `ai.py`：`ModelConfigUpdate.require_http_url` 限制模型提供商为 HTTP(S)；`ProblemTaskCreate`
  校验命题需求；`AIUsage` 保存输入/输出 Token、总量和费用；`AIProblemTask` 保存任务状态、
  结果和错误。
- `problem.py`：`TestCase` 校验输入输出；`ProblemCreate` 校验完整题面；`Problem` 表示存储
  题目；`ProblemUpdate.require_edit` 防止空更新或只修改 ID。
- `submission.py`：`SubmissionCreate` 校验提交代码；`TestCaseResult` 表示单测例；
  `JudgeSnapshot` 冻结提交时的题目和语言；`Submission.validate_created_at` 校验时区时间；
  `Submission.validate_result_totals` 校验分数和测例 ID。
- `user.py`：`Credentials` 校验注册/登录；`RoleUpdate` 校验角色；`User.validate_join_date`
  校验日期；`User.public` 删除密码；`Session` 表示服务端会话。
- `language.py`：`LanguageCreate.normalize_extension` 规范化扩展名；`Language` 表示语言配置。
- `log.py`：`AccessLog` 表示日志访问审计记录。
- `plagiarism.py`：`PlagiarismRequest`、`PlagiarismMatch`、`PlagiarismTask` 分别表示查重
  请求、匹配节点和任务结果。
- `system.py`：`ImportBundle` 校验导入的 users/problems/submissions 固定结构。

### 3.6 业务 Service（`app/services/`）

- `auth_service.py`：`AuthService.login` 查找并校验用户；`create_session` 创建带过期时间的
  Session；`logout` 删除会话；`remove` 是删除会话的 Store 操作；`current_user` 从会话取
  用户并拒绝过期或 banned 用户。
- `user_service.py`：`create_user` 检查用户名、哈希密码并创建用户；内部 `create` 执行原子
  写入；`get_user` 查用户；`list_users` 统计并分页；`update_role` 修改角色，内部 `update`
  执行原子更新。
- `problem_service.py`：`list_problems` 返回摘要；`get_problem` 读取详情；`add_problem`
  新增并检查 ID；`delete_problem` 删除题目及 SPJ；`update_problem` 合并并重新校验题面；
  `set_log_visibility` 设置公开性；`spj_path` 计算 SPJ 路径；`save_spj` 校验脚本 AST、导入
  和危险操作；`delete_spj` 删除脚本；`_write_spj` 原子写脚本；`_set_judge_mode` 更新判题模式。
- `language_service.py`：`list_languages` 列出语言名；`get_language` 查询语言；`register`
  校验配置并写入；内部 `add` 执行原子新增。
- `submission_service.py`：`submit` 做频率限制、资源查找和快照；`get_submission` 读取提交；
  `result_for` 按权限返回结果；`list_submissions` 筛选分页；`rejudge` 重置原记录并刷新快照；
  `resume_pending` 恢复未完成任务；`shutdown` 取消任务；`wait` 等待终态；`_schedule` 管理
  asyncio Task；`_evaluate` 调用 Runner 并写入分数、详情和任务级信息。
- `log_service.py`：`get_log` 执行日志权限裁剪并审计；`list_access_logs` 筛选分页审计；
  `_record` 写入一次访问记录。
- `system_service.py`：`initialize` 建立初始管理员和 Python/C++；`reset` 清空并重建；
  `export_data` 生成官方固定格式；`import_data` 原子合并；`validate_import` 先行校验；
  `_validate_import_against_state` 校验重复 ID、哈希和引用；`_merge` 按 ID 覆盖；
  `_initial_admin` 返回初始管理员。
- `state_helpers.py`：`next_numeric_id` 生成下一个数字 ID；`recompute_user_stats` 重算提交数
  和通过题数。
- `ai_service.py`：`AIProblemService.set_config/get_config` 管理进程内模型配置；`create/get`
  创建和读取任务；`cancel` 取消真实后台协程；`shutdown` 清理任务和密钥；`_set_progress`
  更新阶段；`_generate` 执行完整命题流程；`_build_messages` 构造题目约束 Prompt；
  `_request_model` 异步调用 OpenAI 兼容 Chat Completions；`_parse_response` 校验 JSON 题面
  并计算 Token 费用。`_RuntimeModelConfig.public` 生成不含密钥的配置响应。
- `plagiarism_service.py`：`start` 创建查重任务；`resume_pending` 恢复任务；`shutdown` 停止
  任务；`get` 查询结果；`report_path` 校验报告路径；`_analyze` 执行 PDG 比较并生成报告。

### 3.7 评测和查重算法

- `judge/runner.py`：`JudgeRunner.judge` 逐测例编译、运行和比较；`_resolve_limits` 按题目→语言
  →系统解析限制；`_uses_docker` 选择后端；`_run_command` 构造本地/Docker 命令；`_execute`
  执行并监控进程；`_communicate_limited` 限制输出并传入 stdin，其中闭包 `feed_input` 写入
  测试输入、`read_stream` 读取受限输出；`_memory_limiter` 和其闭包 `apply_limit`、
  `_monitor_memory` 监控/限制内存；`_is_killed_returncode`、
  `_looks_like_memory_error` 分类异常；`_kill_process_tree` 和 `_kill_docker_container` 清理
  进程；`_compare_output` 比较标准/strict 输出；`_run_spj` 执行 SPJ；`_normalize` 归一化末尾空格。
  `ProcessResult` 保存一次进程执行结果。
- `plagiarism/pdg.py`：`build_pdg` 按语言选择 AST 或 token 图；`_build_python_pdg` 构造节点和
  控制流，其中闭包 `add_node` 加节点、`build_block` 构造语句块；`_reaching_definition_edges`
  连接数据依赖；`edge_features` 提取边特征；`graph_similarity` 计算图相似度；
  `map_similar_nodes` 映射匹配节点；`_multiset_jaccard` 计算多重集合相似度；
  `_normalized_ast_label`、`_statement_header`、`_names` 规范化 AST；`Normalizer.visit_Name`、
  `visit_arg`、`visit_Constant` 规范化变量/参数/常量；`_build_token_pdg` 为非 Python 语言生成
  token 图。

### 3.8 前端（`frontend/app.py`）

`api` 统一发送带 Cookie 的 REST 请求并处理错误；`show_submission` 展示状态、分数、编译、
运行、错误和测例日志；`problem_form` 负责题目新增/编辑/AI 结果审阅表单；`render_ai_progress`
每秒轮询 AI 任务、显示进度和费用，并提供真实中断按钮。页面分为题库、提交与评测、题目管理、
用户、AI 智能命题五个 Tab。

## 4. 课程要求对应关系

| 课程要求 | 对应文件 |
| --- | --- |
| Step 1 题目配置、校验、增删改查 | `app/models/problem.py`、`app/api/problems.py`、`app/services/problem_service.py` |
| Step 2 Python/C++、动态语言、资源限制 | `app/judge/runner.py`、`app/api/languages.py`、`app/services/language_service.py` |
| Step 3 列表、筛选、状态、重判 | `app/api/submissions.py`、`app/services/submission_service.py` |
| Step 4 注册、登录、角色、分页 | `app/api/auth.py`、`app/api/users.py`、`app/services/auth_service.py`、`app/services/user_service.py` |
| Step 5 测例日志、公开性、审计 | `app/api/logs.py`、`app/services/log_service.py`、`app/models/log.py` |
| Step 6 用户/题目/评测前端 | `frontend/app.py` |
| AI R1 出题界面和结果入库 | `app/api/ai.py`、`app/services/ai_service.py`、`frontend/app.py` |
| AI R2 自定义模型配置和密钥保护 | `app/models/ai.py`、`app/services/ai_service.py` |
| AI R3 实时进度和真实中断 | `AIProblemService._generate/cancel`、`render_ai_progress` |
| AI R4 Token 和费用统计 | `AIProblemService._parse_response`、`AIUsage`、`render_ai_progress` |
| 统一状态码和响应结构 | `app/core/exceptions.py`、`app/core/responses.py` |
| 持久化、reset、导入导出 | `app/repositories/state_store.py`、`app/services/system_service.py` |
| SPJ（额外功能） | `app/services/problem_service.py`、`app/judge/runner.py` |
| Docker（额外功能） | `docker/`、`scripts/build_judge_images.sh`、`app/judge/runner.py` |
| PDG 查重（额外功能） | `app/plagiarism/pdg.py`、`app/services/plagiarism_service.py` |

## 5. Docker 镜像脚本说明

`scripts/build_judge_images.sh` 不是 Python 代码，而是用于构建 Docker 隔离判题镜像的 shell 脚本：它读取
`docker/judge-python.Dockerfile` 和 `docker/judge-cpp.Dockerfile`，分别生成 `oj-python:3.10`
和 `oj-cpp:gcc13`。课程没有要求必须使用 WSL/Linux；Windows CMD 可以完成基础开发、运行和验收。
只有在需要构建 Docker 隔离判题镜像时，才需要 Docker Desktop、WSL 或 Linux 中任一可用的 Docker 运行环境：

```bash
./scripts/build_judge_images.sh
OJ_JUDGE_BACKEND=docker uvicorn app.main:app
```

脚本有用，应保留并提交；`note.md` 只是个人命令笔记，已加入 `.gitignore`，不提交。

## 6. 验证和提交前检查

```cmd
python -m compileall -q app tests frontend
python -m pytest -q
git diff --check
git status
```

当前 Windows 环境结果：`68 passed, 1 skipped`。跳过项是仅能在 POSIX 系统验证的进程组测试；
如需验证 Docker/POSIX 进程组等环境特性，可在 Linux/WSL 或启用 Docker Desktop 后额外执行，
这不是课程硬性要求。真实 AI 模型调用、Docker daemon 和页面截图需要在验收前人工完成。

课程页面：[实验概述](https://dbg-course.github.io/python-docs/oj/)、[API 文档](https://dbg-course.github.io/python-docs/oj/api/)、
[评分标准](https://dbg-course.github.io/python-docs/oj/requirements/)、[AI 智能命题](https://dbg-course.github.io/python-docs/oj/project/advance/)。

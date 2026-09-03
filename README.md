# Python Course OJ

一个使用 FastAPI 异步接口实现的小型 Online Judge。项目覆盖课程基础 Step1–6，并实现
Special Judge、Streamlit 前端、Docker 沙箱和基于程序依赖图（PDG）的代码查重。

## 功能

- 题目：创建、列表、详情、删除、日志可见性。
- 评测：Python/C++、动态语言、后台任务、AC/WA/RE/CE/TLE/MLE/UNK、重判。
- 用户：注册、Cookie Session、登录/登出、三种角色、用户统计、分页。
- 日志：逐测例结果、权限裁剪、访问审计。
- 数据：原子 JSON 持久化、重启恢复、重置、导入、导出。
- 进阶：SPJ、Streamlit、Docker 隔离、PDG 查重及 JSON 报告。

所有课程 API 都由 `async def` 定义；成功和失败响应均使用
`{"code": ..., "msg": ..., "data": ...}`，HTTP 状态码与 `code` 一致。

## 项目结构

```text
app/
├── api/             # HTTP 路由：解析请求、调用服务、组织响应
├── core/            # 配置、异常、分页、密码和命令安全
├── judge/           # 本地/Docker 进程执行、资源监控、输出比对、SPJ
├── models/          # Pydantic 请求与持久化模型
├── plagiarism/      # AST/CFG/PDG 构造、图特征相似度和节点映射
├── repositories/    # 带锁和原子替换的 JSON 状态存储
├── services/        # 业务规则、权限后的数据操作、后台任务
├── container.py     # 服务对象装配及生命周期
└── main.py          # FastAPI 应用工厂和路由注册
frontend/app.py      # Streamlit 前端
docker/              # Python/C++ 专用评测镜像
scripts/             # 评测镜像构建脚本
tests/               # 单元与端到端测试
docs/                # 安全说明、要求对照和实验报告草稿
```

运行数据保存在 `data/state.json`，SPJ 和查重报告分别保存在 `data/spj/`、
`data/reports/`。整个 `data/` 已被 Git 忽略，不会误交评测数据或用户代码。

## 环境与安装

推荐 Linux/WSL、Python 3.10+、GCC 9+。Windows PowerShell：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Linux/macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

启动后端：

```bash
uvicorn app.main:app --reload
```

- 健康检查：<http://127.0.0.1:8000/health>
- Swagger API：<http://127.0.0.1:8000/docs>
- 初始管理员：`admin` / `admintestpassword`

启动 Streamlit 前端：

```bash
python -m pip install -r requirements-frontend.txt
streamlit run frontend/app.py
```

## API 一览

| 方法 | 路径 | 权限 | 作用 |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | 公开 | 登录并设置 Session Cookie |
| POST | `/api/auth/logout` | 登录 | 注销服务端 Session |
| POST | `/api/users/` | 公开 | 注册用户 |
| POST | `/api/users/admin` | 管理员 | 创建管理员 |
| GET | `/api/users/{user_id}` | 本人/管理员 | 查询用户 |
| GET | `/api/users/` | 管理员 | 分页查询用户 |
| PUT | `/api/users/{user_id}/role` | 管理员 | 修改角色 |
| GET/POST | `/api/problems/` | 登录 | 列表/创建题目 |
| GET | `/api/problems/{problem_id}` | 登录 | 题目详情 |
| DELETE | `/api/problems/{problem_id}` | 管理员 | 删除题目 |
| PUT | `/api/problems/{problem_id}/log_visibility` | 管理员 | 日志可见性 |
| GET/POST | `/api/languages/` | 登录 | 查询/注册语言 |
| POST | `/api/submissions/` | 登录 | 创建异步评测 |
| GET | `/api/submissions/{submission_id}` | 本人/管理员 | 总分或任务状态 |
| GET | `/api/submissions/` | 本人/管理员 | 筛选、分页查询 |
| PUT | `/api/submissions/{submission_id}/rejudge` | 管理员 | 原 ID 重新评测 |
| GET | `/api/submissions/{submission_id}/log` | 按可见性 | 测例日志 |
| GET | `/api/logs/access/` | 管理员 | 日志访问审计 |
| POST | `/api/reset/` | 管理员 | 清空并恢复初始状态 |
| GET/POST | `/api/export/`、`/api/import/` | 管理员 | JSON 导出/导入 |
| POST/DELETE | `/api/problems/{problem_id}/spj` | 管理员 | 上传/删除 SPJ |
| POST/GET | `/api/plagiarism/...` | 管理员 | 查重任务、结果和报告 |

详细请求字段以课程 API 文档及 `/docs` 生成的 OpenAPI 为准。

## 评测模式

默认使用本地子进程，适合开发和基础功能验收：

```bash
OJ_JUDGE_BACKEND=local uvicorn app.main:app
```

本地模式有时间、地址空间、进程树和输出量限制，但不能隔离文件和网络，不能用于执行
不可信代码。Advance 3 或真实部署必须显式使用 Docker：

```bash
./scripts/build_judge_images.sh
OJ_JUDGE_BACKEND=docker uvicorn app.main:app
```

Docker 评测禁用网络，设置内存、CPU、PID、只读根文件系统、`no-new-privileges`，并移除
Linux capabilities。Python/C++ 镜像可用以下变量替换：

- `OJ_PYTHON_IMAGE`，默认 `oj-python:3.10`
- `OJ_CPP_IMAGE`，默认 `oj-cpp:gcc13`
- `OJ_SECURE_COOKIES=true`，在 HTTPS 部署中启用 Secure Cookie

## Special Judge 约定

管理员上传 UTF-8 `.py` 脚本后，题目的 `judge_mode` 自动设为 `spj`。脚本收到：

```text
python3 spj.py <input_file> <expected_output_file> <actual_output_file>
```

退出码 `0` 表示 AC，其他退出码表示 WA。脚本最大 256 KB，只允许一组安全标准库导入；
Docker 后端下 SPJ 也在隔离容器内执行。删除脚本后模式恢复 `standard`。

## 数据导入导出

导出只包含课程要求的 `users`、`problems` 和 `submissions`。密码是带随机盐的
PBKDF2-SHA256 哈希，不导出明文。导入会：

1. 完整校验 JSON、字段、哈希、重复 ID/用户名和提交引用；
2. 以 ID 为键合并，冲突时导入数据覆盖原数据；
3. 在一次原子写入中提交，失败不改变原状态；
4. 清除 Session，并恢复导入的 pending 任务。

## 测试与 CI

```bash
python -m compileall -q app tests frontend
python -m pytest -q
```

测试使用临时数据目录，不污染 `data/`。`.gitlab-ci.yml` 会在 Python 3.10 Linux 环境安装
G++ 并运行相同检查。Docker 实际集成测试需要本机 Docker daemon；无 daemon 的常规 CI
仍会检查完整的安全命令构造。

更多内容：

- [安全设计](docs/SECURITY.md)
- [课程要求对照](docs/REQUIREMENTS_CHECKLIST.md)
- [实验报告草稿](docs/COURSE_REPORT.md)

"""Streamlit client for every required OJ workflow."""

import json
from typing import Any

import requests
import streamlit as st


st.set_page_config(page_title="Python Course OJ", page_icon="⚖️", layout="wide")
st.title("Python Course Online Judge")

CASE_RESULT_HELP = {
    "AC": "答案正确（Accepted）",
    "WA": "答案错误（Wrong Answer）",
    "TLE": "超出时间限制（Time Limit Exceeded）",
    "MLE": "超出内存限制（Memory Limit Exceeded）",
    "RE": "运行时错误（Runtime Error）",
    "CE": "编译错误（Compile Error）",
    "UNK": "未知评测错误（Unknown）",
}

for key, default in {
    "api_base": "http://127.0.0.1:8000",
    "http": requests.Session(),
    "user": None,
    "last_submission_id": "",
    "submission_lookup": "",
    "plagiarism_task_id": "",
    "ai_task_id": "",
    "ai_problem_result": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# 复用同一个 requests.Session 发送 API 请求，使登录 Cookie 在所有页面间自动携带。
def api(method: str, path: str, **kwargs: Any) -> Any:
    """Call the backend with the shared cookie session and show safe errors."""
    try:
        response = st.session_state.http.request(
            method,
            f"{st.session_state.api_base.rstrip('/')}{path}",
            timeout=20,
            **kwargs,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {"code": response.status_code, "msg": "invalid server response"}
        if response.status_code >= 400:
            st.error(payload.get("msg", "Request failed"))
            return None
        return payload.get("data")
    except requests.RequestException:
        st.error("Cannot reach the backend. Check the backend URL and server status.")
        return None


# 使用当前登录会话下载受保护文件；失败时在页面提示并返回 None。
def api_download(path: str) -> bytes | None:
    """Download a protected backend artifact with the current login session."""
    try:
        response = st.session_state.http.get(
            f"{st.session_state.api_base.rstrip('/')}{path}", timeout=20
        )
        if response.status_code >= 400:
            try:
                message = response.json().get("msg", "下载失败")
            except ValueError:
                message = "下载失败"
            st.error(message)
            return None
        return response.content
    except requests.RequestException:
        st.error("Cannot reach the backend. Check the backend URL and server status.")
        return None


# 把稳定题号和可读标题组合成下拉框标签，同时保留按题号检索的能力。
def problem_label(problem_id: str, problems_by_id: dict[str, dict[str, Any]]) -> str:
    """Combine the searchable stable ID and the human-readable title."""
    problem = problems_by_id.get(problem_id, {})
    title = problem.get("title", "")
    return f"{problem_id} — {title}" if title else problem_id


# 将 submission 的任务状态与测例 verdict 分开：成功任务取第一个非 AC 测例作为总结果。
def submission_verdict(detail: dict[str, Any], cases: list[dict[str, Any]]) -> str:
    """Keep task status and judge verdict separate in the UI."""
    if detail["status"] == "pending":
        return "PENDING"
    if detail["status"] == "error":
        return "SYSTEM_ERROR"
    for case in cases:
        if case.get("result") != "AC":
            return str(case.get("result", "UNK"))
    return "AC" if cases else "结果已隐藏"


# 查询有权查看的评测日志，并集中展示用户、总状态、得分、编译信息和逐测例资源用量。
def show_submission(detail: dict[str, Any]) -> None:
    log = None
    cases: list[dict[str, Any]] = []
    if detail["status"] != "pending":
        log = api("GET", f"/api/submissions/{detail['submission_id']}/log")
        if log and isinstance(log.get("details"), list):
            cases = log["details"]

    st.subheader(f"提交 #{detail['submission_id']}")
    st.caption(
        f"用户 ID：`{detail.get('user_id', '-')}`　"
        f"题目：`{detail.get('problem_id', '-')}`　"
        f"语言：`{detail.get('language', '-')}`　"
        f"提交时间：`{detail.get('created_at', '-')}`"
    )
    status_col, verdict_col = st.columns(2)
    status_col.metric("评测任务状态", detail["status"])
    verdict_col.metric("判题结果", submission_verdict(detail, cases))
    if detail["status"] == "pending":
        st.info("评测正在后台运行，本区域会每秒自动刷新，完成后直接显示最终结果。")
        return

    case_count = int(detail.get("counts", 0))
    maximum_score = case_count * 10
    score_col, count_col = st.columns(2)
    score_col.metric("得分 / 满分", f"{detail.get('score', 0)} / {maximum_score}")
    count_col.metric("测试点个数（counts）", case_count)
    st.caption("counts 表示测试点个数；课程规定每个测试点 10 分，因此 counts=3 时满分为 30 分。")

    compile_col, run_col = st.columns(2)
    with compile_col:
        st.write("编译信息")
        if detail.get("compile_info"):
            st.json(detail["compile_info"])
        else:
            st.info("解释型语言没有单独的编译阶段。")
    with run_col:
        st.write("整体运行信息")
        st.json(detail.get("run_info") or {"result": "暂无", "message": ""})
    if detail.get("error_info"):
        st.error(detail["error_info"])

    st.write("评测点结果")
    if cases:
        rows = [
            {
                "测试点": case["id"],
                "状态": case["result"],
                "状态说明": CASE_RESULT_HELP.get(case["result"], "未知"),
                "时间（秒）": f"{float(case['time']):.4f}",
                "内存（MB）": f"{float(case['memory']):.2f}",
            }
            for case in cases
        ]
        st.dataframe(rows, width="stretch", hide_index=True)
        st.caption(
            "状态缩写："
            + "；".join(f"{key}={value}" for key, value in CASE_RESULT_HELP.items())
        )
    else:
        st.info("测试点详情未公开。管理员可查看；普通用户需等待该题开启“公开测试点日志”。")


# 用同一份表单处理新建和编辑，解析样例/测例 JSON 后返回课程题目配置结构。
def problem_form(seed: dict[str, Any] | None, form_key: str) -> dict[str, Any] | None:
    seed = seed or {}
    seed_id = str(seed.get("id", ""))
    legacy_id = bool(seed_id and not seed_id.isdigit())
    with st.form(form_key):
        if legacy_id:
            problem_id: int | str = st.text_input(
                "题目 ID（历史字符串 ID）", value=seed_id, disabled=True
            )
            st.caption("这是通过课程接口导入的历史字符串 ID；新建题目统一使用整数 ID。")
        else:
            problem_id = int(
                st.number_input(
                    "题目 ID（整数）",
                    min_value=1,
                    value=int(seed_id) if seed_id else 1001,
                    step=1,
                    help="例如 1001。ID 用于唯一标识和检索题目。",
                )
            )
        title = st.text_input("标题", value=seed.get("title", ""))
        description = st.text_area("题目描述", value=seed.get("description", ""))
        input_description = st.text_area("输入说明", value=seed.get("input_description", ""))
        output_description = st.text_area("输出说明", value=seed.get("output_description", ""))
        constraints = st.text_area("数据范围", value=seed.get("constraints", ""))
        samples = st.text_area(
            "样例（JSON 数组）",
            value=json.dumps(seed.get("samples", []), ensure_ascii=False, indent=2),
        )
        testcases = st.text_area(
            "测试点（JSON 数组）",
            value=json.dumps(seed.get("testcases", []), ensure_ascii=False, indent=2),
            height=220,
        )
        st.markdown("**可选字段**")
        tags = st.text_input("标签（逗号分隔）", value=", ".join(seed.get("tags", [])))
        c1, c2 = st.columns(2)
        time_limit = c1.number_input(
            "时间限制（秒）", min_value=0.1, value=float(seed.get("time_limit") or 3.0)
        )
        memory_limit = c2.number_input(
            "内存限制（MB）", min_value=1, value=int(seed.get("memory_limit") or 128)
        )
        hint = st.text_input("提示", value=seed.get("hint", ""))
        source = st.text_input("来源", value=seed.get("source", ""))
        author = st.text_input("作者", value=seed.get("author", ""))
        difficulty = st.text_input("难度", value=seed.get("difficulty", ""))
        submitted = st.form_submit_button("提交题目配置", type="primary")
    if not submitted:
        return None
    try:
        parsed_samples = json.loads(samples)
        parsed_testcases = json.loads(testcases)
        if not isinstance(parsed_samples, list) or not isinstance(parsed_testcases, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        st.error("样例和测试点必须是 JSON 数组。")
        return None
    return {
        "id": problem_id,
        "title": title.strip(),
        "description": description,
        "input_description": input_description,
        "output_description": output_description,
        "samples": parsed_samples,
        "constraints": constraints,
        "testcases": parsed_testcases,
        "hint": hint,
        "source": source,
        "tags": [tag.strip() for tag in tags.split(",") if tag.strip()],
        "time_limit": time_limit,
        "memory_limit": memory_limit,
        "author": author,
        "difficulty": difficulty,
    }


# 通过 Streamlit Fragment 每秒轮询 AI 任务，并提供中断、用量展示和结果回填。
@st.fragment(run_every=1.0)
def render_ai_progress() -> None:
    """Poll independently so progress remains live and the cancel button works."""
    task_id = st.session_state.ai_task_id
    if not task_id:
        return
    task = api("GET", f"/api/ai/problem-tasks/{task_id}")
    if not task:
        return
    st.subheader("任务进度")
    st.write(f"状态：`{task['status']}` — {task['progress']}")
    if task["status"] in {"pending", "running"}:
        st.progress(0.5, text=task["progress"])
        if st.button("中断当前任务"):
            api("PUT", f"/api/ai/problem-tasks/{task_id}/cancel")
            st.rerun(scope="fragment")
    elif task["status"] == "success":
        st.session_state.ai_problem_result = task["result"]
        usage = task["usage"]
        c1, c2, c3 = st.columns(3)
        c1.metric("输入 Token", usage["input_tokens"])
        c2.metric("输出 Token", usage["output_tokens"])
        c3.metric("费用 (USD)", f"{usage['cost']:.8f}")
        st.json(task["result"])
        st.success("结果已送入“题目管理 → 使用 AI 结果”，可继续审阅和保存。")
    elif task["status"] == "cancelled":
        st.warning("任务已中断。")
    else:
        st.error(task.get("error") or "命题失败")


# 在提交页面独立轮询最近一次提交，使整页操作不会清空结果，并自动展示状态变化。
@st.fragment(run_every=1.0)
def render_submission_progress() -> None:
    submission_id = str(st.session_state.get("submission_lookup", "")).strip()
    if not submission_id:
        st.caption("提交代码后，评测过程和最终结果会显示在这里。")
        return
    detail = api("GET", f"/api/submissions/{submission_id}")
    if detail:
        show_submission(detail)


with st.sidebar:
    st.text_input("后端地址", key="api_base")
    if st.session_state.user:
        st.success(f"已登录：{st.session_state.user['username']}")
        if st.button("退出登录"):
            api("POST", "/api/auth/logout")
            st.session_state.user = None
            st.rerun()

if not st.session_state.user:
    login_tab, register_tab = st.tabs(["登录", "注册"])
    with login_tab:
        with st.form("login"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            if st.form_submit_button("登录", type="primary"):
                user = api(
                    "POST",
                    "/api/auth/login",
                    json={"username": username, "password": password},
                )
                if user:
                    st.session_state.user = user
                    st.rerun()
    with register_tab:
        with st.form("register"):
            new_username = st.text_input("新用户名")
            new_password = st.text_input("新密码", type="password")
            if st.form_submit_button("创建账户"):
                created = api(
                    "POST", "/api/users/", json={"username": new_username, "password": new_password}
                )
                if created:
                    st.success("注册成功，请返回登录。")
    st.stop()

# 后端角色可能被管理员修改；每次刷新页面都同步当前用户，避免前端保留旧权限。
fresh_user = api("GET", f"/api/users/{st.session_state.user['user_id']}")
if fresh_user:
    st.session_state.user = fresh_user

problems = api("GET", "/api/problems/") or []
languages = api("GET", "/api/languages/") or {"name": ["python"]}
problem_ids = [item["id"] for item in problems]
problems_by_id = {item["id"]: item for item in problems}
format_problem = lambda problem_id: problem_label(problem_id, problems_by_id)

(
    browse_tab,
    submit_tab,
    records_tab,
    manage_tab,
    language_tab,
    advanced_tab,
    account_tab,
    ai_tab,
) = st.tabs(
    [
        "题库",
        "提交与评测",
        "提交记录",
        "题目管理",
        "语言管理",
        "查重 / Special Judge",
        "用户",
        "AI 智能命题",
    ]
)

with browse_tab:
    if not problem_ids:
        st.info("题库暂无题目，可在“题目管理”中新建。")
    else:
        problem_id_query = st.text_input(
            "按题目 ID 搜索", placeholder="输入完整 ID 或其中一部分，例如 1001"
        ).strip()
        matched_problem_ids = [
            problem_id
            for problem_id in problem_ids
            if not problem_id_query or problem_id_query in str(problem_id)
        ]
        browse_id = None
        if not matched_problem_ids:
            st.warning("没有找到匹配的题目 ID。")
        else:
            browse_id = st.selectbox(
                "选择题目",
                matched_problem_ids,
                key="browse_problem",
                format_func=format_problem,
            )
        problem = api("GET", f"/api/problems/{browse_id}") if browse_id else None
        if problem:
            st.header(f"{problem['id']} — {problem['title']}")
            meta_col1, meta_col2, meta_col3, meta_col4 = st.columns(4)
            meta_col1.metric("时间限制", f"{problem.get('time_limit') or 3} 秒")
            meta_col2.metric("内存限制", f"{problem.get('memory_limit') or 128} MB")
            meta_col3.metric("难度", problem.get("difficulty") or "未设置")
            meta_col4.metric("判题模式", problem.get("judge_mode", "standard"))
            tags = problem.get("tags") or []
            if tags:
                st.caption("标签：" + "、".join(tags))
            optional_parts = [
                f"来源：{problem['source']}" if problem.get("source") else "",
                f"作者：{problem['author']}" if problem.get("author") else "",
            ]
            if any(optional_parts):
                st.caption("　".join(part for part in optional_parts if part))
            st.write(problem["description"])
            st.subheader("输入")
            st.write(problem["input_description"])
            st.subheader("输出")
            st.write(problem["output_description"])
            st.caption(f"限制：{problem['constraints']}")
            if problem.get("hint"):
                st.info(f"提示：{problem['hint']}")
            for index, sample in enumerate(problem.get("samples", []), start=1):
                left, right = st.columns(2)
                left.caption(f"样例输入 {index}")
                right.caption(f"样例输出 {index}")
                left.code(sample["input"], language="text")
                right.code(sample["output"], language="text")

with submit_tab:
    if not problem_ids:
        st.info("请先创建题目。")
    else:
        with st.form("submit_code"):
            submit_problem = st.selectbox(
                "题目", problem_ids, key="submit_problem", format_func=format_problem
            )
            language = st.selectbox("语言", languages.get("name", ["python"]))
            code = st.text_area("代码", height=300)
            if st.form_submit_button("提交评测", type="primary"):
                result = api(
                    "POST",
                    "/api/submissions/",
                    json={"problem_id": submit_problem, "language": language, "code": code},
                )
                if result:
                    submission_id = str(result["submission_id"])
                    st.session_state.last_submission_id = submission_id
                    st.session_state.submission_lookup = submission_id
                    st.rerun()

        lookup_id = st.text_input(
            "提交 ID",
            key="submission_lookup",
            help="默认保留最近一次提交，也可以输入其他提交 ID 查询。",
        )
        st.button("立即刷新", disabled=not lookup_id.strip())
        render_submission_progress()

with records_tab:
    st.subheader("提交记录查询与筛选")
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    if st.session_state.user["role"] == "admin":
        records_users = api("GET", "/api/users/") or {"users": []}
        record_user_ids = [item["user_id"] for item in records_users.get("users", [])]
        default_user_index = (
            record_user_ids.index(st.session_state.user["user_id"]) + 1
            if st.session_state.user["user_id"] in record_user_ids
            else 0
        )
        filter_user_id = filter_col1.selectbox(
            "用户 ID（管理员可选）",
            [""] + record_user_ids,
            index=default_user_index,
            format_func=lambda value: "全部用户" if value == "" else value,
        )
    else:
        filter_user_id = st.session_state.user["user_id"]
        filter_col1.text_input("用户 ID", value=filter_user_id, disabled=True)
    filter_problem_id = filter_col2.selectbox(
        "题目",
        [""] + problem_ids,
        format_func=lambda value: "全部题目" if value == "" else format_problem(value),
    )
    status_options = ["", "pending", "success", "error"]
    filter_status = filter_col3.selectbox(
        "评测任务状态",
        status_options,
        format_func=lambda value: "全部状态" if value == "" else value,
    )
    page_col, size_col = st.columns(2)
    record_page = int(page_col.number_input("页码", min_value=1, value=1, step=1))
    record_page_size = int(
        size_col.number_input("每页数量", min_value=1, max_value=100, value=20, step=1)
    )

    history = None
    if filter_user_id or filter_problem_id:
        query = {
            "user_id": filter_user_id or None,
            "problem_id": filter_problem_id or None,
            "status": filter_status or None,
            "page": record_page,
            "page_size": record_page_size,
        }
        history = api("GET", "/api/submissions/", params=query)
    else:
        st.info("课程接口要求 user_id 和 problem_id 至少填写一个；请选择一个题目或用户。")

    if history and history.get("submissions"):
        records = history["submissions"]
        st.write(f"共 {history['total']} 条记录")
        st.dataframe(records, width="stretch", hide_index=True)
        selected_submission = st.selectbox(
            "选择一条记录查看完整结果",
            [item["submission_id"] for item in records],
            key="record_submission",
        )
        action_col, rejudge_col = st.columns(2)
        if action_col.button("查看完整评测详情", type="primary"):
            selected_detail = api("GET", f"/api/submissions/{selected_submission}")
            if selected_detail:
                show_submission(selected_detail)
        if st.session_state.user["role"] == "admin":
            if rejudge_col.button("管理员重判此记录"):
                rejudged = api("PUT", f"/api/submissions/{selected_submission}/rejudge")
                if rejudged:
                    st.success(f"提交 {selected_submission} 已进入 pending，评测将在后台重新执行。")
                    st.rerun()
    elif history:
        st.caption("当前筛选条件下没有提交记录。")

with manage_tab:
    mode_options = ["新增题目"]
    if problem_ids:
        mode_options.append("编辑题目")
    if st.session_state.ai_problem_result:
        mode_options.append("使用 AI 结果")
    mode = st.radio("操作", mode_options, horizontal=True)
    seed = None
    target_id = ""
    if mode == "编辑题目":
        target_id = st.selectbox(
            "待编辑题目", problem_ids, key="edit_problem", format_func=format_problem
        )
        seed = api("GET", f"/api/problems/{target_id}")
    elif mode == "使用 AI 结果":
        seed = st.session_state.ai_problem_result
    payload = problem_form(seed, f"problem_form_{mode}_{target_id or 'new'}")
    if payload:
        saved = (
            api("PUT", f"/api/problems/{target_id}", json=payload)
            if mode == "编辑题目"
            else api("POST", "/api/problems/", json=payload)
        )
        if saved:
            st.success("题目已保存。")

    if st.session_state.user["role"] == "admin" and problem_ids:
        st.divider()
        st.subheader("管理员操作")
        admin_problem = st.selectbox(
            "题目", problem_ids, key="admin_problem", format_func=format_problem
        )
        public_cases = st.checkbox("公开测试点日志")
        if st.button("更新日志可见性"):
            updated = api(
                "PUT",
                f"/api/problems/{admin_problem}/log_visibility",
                json={"public_cases": public_cases},
            )
            if updated:
                st.success("日志可见性已更新。")
        confirm_delete = st.checkbox("我确认删除所选题目")
        if st.button("删除题目", disabled=not confirm_delete):
            if api("DELETE", f"/api/problems/{admin_problem}"):
                st.success("题目已删除。")
                st.rerun()

with language_tab:
    st.subheader("动态注册新语言")
    st.caption("课程要求所有已登录用户都可以注册语言。命令中的 {src} 表示源码，{exe} 表示编译产物。")
    st.write("当前语言：" + "、".join(languages.get("name", [])))
    with st.form("register_language"):
        language_name = st.text_input("语言名称", placeholder="例如：python_copy")
        file_ext = st.text_input("源码扩展名", placeholder="例如：.py")
        compile_cmd = st.text_input(
            "编译命令（解释型语言可留空）",
            placeholder="例如：g++ {src} -O2 -std=c++14 -o {exe}",
        )
        run_cmd = st.text_input(
            "运行命令",
            placeholder="例如：python3 {src}；编译型语言可填写 {exe}",
        )
        limit_col1, limit_col2 = st.columns(2)
        language_time_limit = limit_col1.text_input(
            "语言时间限制（秒，可留空继承系统设置）"
        )
        language_memory_limit = limit_col2.text_input(
            "语言内存限制（MB，可留空继承系统设置）"
        )
        register_language = st.form_submit_button("注册语言", type="primary")
    if register_language:
        try:
            parsed_time_limit = (
                float(language_time_limit) if language_time_limit.strip() else None
            )
            parsed_memory_limit = (
                int(language_memory_limit) if language_memory_limit.strip() else None
            )
            if parsed_time_limit is not None and parsed_time_limit <= 0:
                raise ValueError
            if parsed_memory_limit is not None and parsed_memory_limit <= 0:
                raise ValueError
        except ValueError:
            st.error("时间和内存限制必须留空或填写大于 0 的数字。")
        else:
            registered = api(
                "POST",
                "/api/languages/",
                json={
                    "name": language_name.strip(),
                    "file_ext": file_ext.strip(),
                    "compile_cmd": compile_cmd.strip() or None,
                    "run_cmd": run_cmd.strip(),
                    "time_limit": parsed_time_limit,
                    "memory_limit": parsed_memory_limit,
                },
            )
            if registered:
                st.success(f"语言 {registered['name']} 已注册，可立即用于提交。")
                st.rerun()

with advanced_tab:
    st.subheader("代码查重与 Special Judge")
    if st.session_state.user["role"] != "admin":
        st.info("这些高级功能只允许管理员操作。")
    elif not problem_ids:
        st.info("请先创建题目。")
    else:
        spj_section, plagiarism_section = st.tabs(["Special Judge", "代码查重"])

        with spj_section:
            st.write("为输出存在多种正确形式的题目上传 Python 特判脚本。")
            spj_problem_id = st.selectbox(
                "SPJ 题目",
                problem_ids,
                format_func=format_problem,
                key="spj_problem",
            )
            spj_problem = api("GET", f"/api/problems/{spj_problem_id}")
            if spj_problem:
                st.metric("当前判题模式", spj_problem.get("judge_mode", "standard"))
            with st.expander("查看 SPJ 脚本参数示例"):
                st.code(
                    """import sys
from pathlib import Path

input_text = Path(sys.argv[1]).read_text(encoding="utf-8")
expected = Path(sys.argv[2]).read_text(encoding="utf-8")
actual = Path(sys.argv[3]).read_text(encoding="utf-8")

# 返回码 0 表示 AC，其他返回码表示 WA
raise SystemExit(0 if sorted(expected.split()) == sorted(actual.split()) else 1)
""",
                    language="python",
                )
            uploaded_spj = st.file_uploader(
                "上传 .py 特判脚本", type=["py"], key="spj_upload"
            )
            upload_col, delete_col = st.columns(2)
            if upload_col.button("上传并启用 SPJ", disabled=uploaded_spj is None):
                uploaded = api(
                    "POST",
                    f"/api/problems/{spj_problem_id}/spj",
                    files={
                        "file": (
                            uploaded_spj.name,
                            uploaded_spj.getvalue(),
                            "text/x-python",
                        )
                    },
                )
                if uploaded:
                    st.success("SPJ 已上传，该题已切换为 spj 判题模式。")
                    st.rerun()
            if delete_col.button(
                "删除 SPJ 并恢复标准判题",
                disabled=not spj_problem or spj_problem.get("judge_mode") != "spj",
            ):
                deleted = api("DELETE", f"/api/problems/{spj_problem_id}/spj")
                if deleted:
                    st.success("SPJ 已删除，该题已恢复 standard 判题模式。")
                    st.rerun()

        with plagiarism_section:
            st.write("按题目比较所有提交的程序依赖图，并按相似度找出疑似重复代码。")
            plagiarism_problem_id = st.selectbox(
                "查重题目",
                problem_ids,
                format_func=format_problem,
                key="plagiarism_problem",
            )
            threshold = st.slider(
                "相似度阈值", min_value=0.0, max_value=1.0, value=0.8, step=0.05
            )
            if st.button("开始查重", type="primary"):
                task = api(
                    "POST",
                    "/api/plagiarism/",
                    json={"problem_id": plagiarism_problem_id, "threshold": threshold},
                )
                if task:
                    st.session_state.plagiarism_task_id = task["task_id"]
                    st.rerun()

            task_id = st.text_input(
                "查重任务 ID",
                value=st.session_state.plagiarism_task_id,
                key="plagiarism_lookup",
            )
            st.button("查询/刷新查重结果", disabled=not task_id.strip())
            if task_id.strip():
                plagiarism = api("GET", f"/api/plagiarism/{task_id.strip()}")
                if plagiarism:
                    st.write(f"任务状态：`{plagiarism['status']}`")
                    if plagiarism["status"] == "pending":
                        st.info("查重正在后台执行，请稍后点击刷新。")
                    elif plagiarism["status"] == "error":
                        st.error("查重任务执行失败。")
                    else:
                        count_col1, count_col2, count_col3 = st.columns(3)
                        count_col1.metric("提交数量", plagiarism["submission_count"])
                        count_col2.metric("比较对数", plagiarism["pair_count"])
                        count_col3.metric("疑似重复对数", plagiarism["clone_count"])
                        matches = plagiarism.get("matches", [])
                        if matches:
                            st.dataframe(
                                [
                                    {
                                        "提交 A": match["left_submission_id"],
                                        "提交 B": match["right_submission_id"],
                                        "相似度": f"{float(match['similarity']):.4f}",
                                        "是否疑似重复": match["is_clone"],
                                        "相似节点数": len(match.get("node_mapping", [])),
                                    }
                                    for match in matches
                                ],
                                width="stretch",
                                hide_index=True,
                            )
                            with st.expander("查看相似节点映射"):
                                st.json(
                                    [
                                        {
                                            "提交 A": match["left_submission_id"],
                                            "提交 B": match["right_submission_id"],
                                            "node_mapping": match.get("node_mapping", []),
                                        }
                                        for match in matches
                                    ]
                                )
                        else:
                            st.caption("没有可比较的提交对。")
                        report = api_download(
                            f"/api/plagiarism/{task_id.strip()}/report"
                        )
                        if report is not None:
                            st.download_button(
                                "下载 JSON 查重报告",
                                data=report,
                                file_name=f"plagiarism-{task_id.strip()}.json",
                                mime="application/json",
                            )

with account_tab:
    current = api("GET", f"/api/users/{st.session_state.user['user_id']}")
    if current:
        st.subheader("我的信息")
        st.json(current)
    if st.session_state.user["role"] == "admin":
        st.subheader("用户管理")
        users = api("GET", "/api/users/")
        if users:
            st.dataframe(users["users"], width="stretch", hide_index=True)
            user_ids = [item["user_id"] for item in users["users"]]
            roles_by_user = {item["user_id"]: item["role"] for item in users["users"]}
            selected_user = st.selectbox("要修改的用户 ID", user_ids)
            with st.form("change_role"):
                roles = ["user", "admin", "banned"]
                role = st.selectbox(
                    "角色",
                    roles,
                    index=roles.index(roles_by_user[selected_user]),
                    key=f"role_for_{selected_user}",
                )
                if st.form_submit_button("更新角色"):
                    updated = api(
                        "PUT", f"/api/users/{selected_user}/role", json={"role": role}
                    )
                    if updated:
                        st.success("角色已更新。")
                        st.rerun()

        with st.expander("创建新的管理员账号"):
            with st.form("create_admin"):
                admin_username = st.text_input("新管理员用户名")
                admin_password = st.text_input("新管理员密码", type="password")
                if st.form_submit_button("创建管理员"):
                    created_admin = api(
                        "POST",
                        "/api/users/admin",
                        json={"username": admin_username, "password": admin_password},
                    )
                    if created_admin:
                        st.success(f"管理员 {created_admin['username']} 已创建。")
                        st.rerun()

        with st.expander("Step 5：测试点日志访问审计"):
            audit_col1, audit_col2 = st.columns(2)
            audit_user_id = audit_col1.text_input("按用户 ID 筛选（可留空）")
            audit_problem_id = audit_col2.selectbox(
                "按题目筛选（可留空）",
                [""] + problem_ids,
                format_func=lambda value: "全部题目" if value == "" else format_problem(value),
                key="audit_problem",
            )
            access_logs = api(
                "GET",
                "/api/logs/access/",
                params={
                    "user_id": audit_user_id or None,
                    "problem_id": audit_problem_id or None,
                },
            )
            if access_logs:
                st.dataframe(access_logs, width="stretch", hide_index=True)
            else:
                st.caption("暂无日志访问记录。")

with ai_tab:
    st.markdown(
        "已预设性价比较高的 **DeepSeek V4 Flash 官方 API**。"
        "请在 [DeepSeek API Keys](https://platform.deepseek.com/api_keys) 创建并复制密钥；"
        "密钥仅保存在后端进程内存中，重启后需要重新填写。"
    )
    with st.form("ai_config"):
        provider_url = st.text_input(
            "OpenAI 兼容 API 地址", value="https://api.deepseek.com"
        )
        model = st.text_input(
            "模型名称",
            value="deepseek-v4-flash",
            help="Flash 比 Pro 便宜且速度更快，能力足以生成结构化 OJ 题目。",
        )
        api_key = st.text_input("模型密钥", type="password")
        c1, c2, c3 = st.columns(3)
        input_price = c1.number_input(
            "输入价格（USD/百万 Token）", min_value=0.0, value=0.44
        )
        output_price = c2.number_input(
            "输出价格（USD/百万 Token）", min_value=0.0, value=1.32
        )
        price_unit = c3.number_input("计价 Token 单位", min_value=1, value=1_000_000)
        st.caption("费用按官方高峰期、输入缓存未命中的价格保守估算，实际扣费以 DeepSeek 账单为准。")
        if st.form_submit_button("保存模型配置"):
            configured = api(
                "PUT",
                "/api/ai/model-config",
                json={
                    "provider_url": provider_url,
                    "model": model,
                    "api_key": api_key,
                    "input_price": input_price,
                    "output_price": output_price,
                    "price_unit": price_unit,
                },
            )
            if configured:
                st.success("模型配置已保存并将用于后续任务。")

    with st.form("ai_problem_task"):
        requirement = st.text_area(
            "命题要求", placeholder="例如：考查二分查找，中等难度，包含重复元素边界情况"
        )
        reference_id = st.selectbox(
            "参考已有题目（可选）",
            [""] + problem_ids,
            format_func=lambda value: "不参考已有题目" if value == "" else format_problem(value),
        )
        if st.form_submit_button("开始智能命题", type="primary"):
            task = api(
                "POST",
                "/api/ai/problem-tasks/",
                json={"requirement": requirement, "problem_id": reference_id or None},
            )
            if task:
                st.session_state.ai_task_id = task["task_id"]
                st.rerun()

    render_ai_progress()

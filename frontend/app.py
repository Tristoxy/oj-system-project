"""Streamlit client for every required OJ workflow."""

import json
from typing import Any

import requests
import streamlit as st


st.set_page_config(page_title="Python Course OJ", page_icon="⚖️", layout="wide")
st.title("Python Course Online Judge")

for key, default in {
    "api_base": "http://127.0.0.1:8000",
    "http": requests.Session(),
    "user": None,
    "last_submission_id": "",
    "ai_task_id": "",
    "ai_problem_result": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# 函数 `api`：统一发送前端 API 请求并处理响应。
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


# 函数 `show_submission`：展示提交记录及其评测详情。
def show_submission(detail: dict[str, Any]) -> None:
    st.write(f"状态：`{detail['status']}`　提交 ID：`{detail['submission_id']}`")
    if detail["status"] == "pending":
        st.info("评测正在后台运行。")
        return
    left, right = st.columns(2)
    left.metric("得分", f"{detail.get('score', 0)} / {detail.get('counts', 0)}")
    right.write("编译信息", detail.get("compile_info") or "解释型语言，无编译阶段")
    st.write("运行信息", detail.get("run_info") or "暂无")
    if detail.get("error_info"):
        st.error(detail["error_info"])
    log = api("GET", f"/api/submissions/{detail['submission_id']}/log")
    if log and "details" in log:
        st.dataframe(log["details"], use_container_width=True, hide_index=True)


# 函数 `problem_form`：渲染题目新增和编辑表单。
def problem_form(seed: dict[str, Any] | None, form_key: str) -> dict[str, Any] | None:
    seed = seed or {}
    with st.form(form_key):
        problem_id = st.text_input("题目 ID", value=seed.get("id", ""))
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
        "id": problem_id.strip(),
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


# 函数 `render_ai_progress`：轮询并展示 AI 命题任务进度。
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
                user = api("POST", "/api/auth/login", json={"username": username, "password": password})
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

problems = api("GET", "/api/problems/") or []
languages = api("GET", "/api/languages/") or {"name": ["python"]}
problem_ids = [item["id"] for item in problems]

browse_tab, submit_tab, manage_tab, account_tab, ai_tab = st.tabs(
    ["题库", "提交与评测", "题目管理", "用户", "AI 智能命题"]
)

with browse_tab:
    if not problem_ids:
        st.info("题库暂无题目，可在“题目管理”中新建。")
    else:
        browse_id = st.selectbox("选择题目", problem_ids, key="browse_problem")
        problem = api("GET", f"/api/problems/{browse_id}")
        if problem:
            st.header(problem["title"])
            st.write(problem["description"])
            st.subheader("输入")
            st.write(problem["input_description"])
            st.subheader("输出")
            st.write(problem["output_description"])
            st.caption(f"限制：{problem['constraints']}")
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
            submit_problem = st.selectbox("题目", problem_ids, key="submit_problem")
            language = st.selectbox("语言", languages.get("name", ["python"]))
            code = st.text_area("代码", height=300)
            if st.form_submit_button("提交评测", type="primary"):
                result = api(
                    "POST",
                    "/api/submissions/",
                    json={"problem_id": submit_problem, "language": language, "code": code},
                )
                if result:
                    st.session_state.last_submission_id = result["submission_id"]
                    st.rerun()

        lookup_id = st.text_input(
            "提交 ID", value=st.session_state.last_submission_id, key="submission_lookup"
        )
        if st.button("查询/刷新", disabled=not lookup_id.strip()):
            detail = api("GET", f"/api/submissions/{lookup_id.strip()}")
            if detail:
                show_submission(detail)
        history = api("GET", f"/api/submissions/?user_id={st.session_state.user['user_id']}")
        st.subheader("我的提交记录")
        if history and history.get("submissions"):
            st.dataframe(history["submissions"], use_container_width=True, hide_index=True)
        else:
            st.caption("暂无提交。")

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
        target_id = st.selectbox("待编辑题目", problem_ids, key="edit_problem")
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
        admin_problem = st.selectbox("题目", problem_ids, key="admin_problem")
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

with account_tab:
    current = api("GET", f"/api/users/{st.session_state.user['user_id']}")
    if current:
        st.subheader("我的信息")
        st.json(current)
    if st.session_state.user["role"] == "admin":
        st.subheader("用户管理")
        users = api("GET", "/api/users/")
        if users:
            st.dataframe(users["users"], use_container_width=True, hide_index=True)
            user_ids = [item["user_id"] for item in users["users"]]
            with st.form("change_role"):
                selected_user = st.selectbox("用户 ID", user_ids)
                role = st.selectbox("角色", ["user", "admin", "banned"])
                if st.form_submit_button("更新角色"):
                    updated = api(
                        "PUT", f"/api/users/{selected_user}/role", json={"role": role}
                    )
                    if updated:
                        st.success("角色已更新。")

with ai_tab:
    st.caption("模型密钥仅保存在后端进程内存中，重启后需要重新配置。")
    with st.form("ai_config"):
        provider_url = st.text_input(
            "OpenAI 兼容 API 地址", placeholder="https://api.openai.com/v1"
        )
        model = st.text_input("模型名称")
        api_key = st.text_input("模型密钥", type="password")
        c1, c2, c3 = st.columns(3)
        input_price = c1.number_input("输入价格", min_value=0.0, value=0.0)
        output_price = c2.number_input("输出价格", min_value=0.0, value=0.0)
        price_unit = c3.number_input("计价 Token 单位", min_value=1, value=1_000_000)
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
        reference_id = st.selectbox("参考已有题目（可选）", [""] + problem_ids)
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

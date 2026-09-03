"""Streamlit client for the OJ backend."""

import time

import requests
import streamlit as st


st.set_page_config(page_title="Python Course OJ", page_icon="⚖️", layout="wide")
st.title("Python Course Online Judge")

if "api_base" not in st.session_state:
    st.session_state.api_base = "http://127.0.0.1:8000"
if "http" not in st.session_state:
    st.session_state.http = requests.Session()
if "user" not in st.session_state:
    st.session_state.user = None
if "last_submission_id" not in st.session_state:
    st.session_state.last_submission_id = None


def api(method: str, path: str, **kwargs):
    try:
        response = st.session_state.http.request(
            method,
            f"{st.session_state.api_base}{path}",
            timeout=15,
            **kwargs,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {"code": response.status_code, "msg": response.text, "data": None}
        if response.status_code >= 400:
            st.error(payload.get("msg", "Request failed"))
            return None
        return payload.get("data")
    except requests.RequestException as exc:
        st.error(f"Cannot reach the backend: {exc}")
        return None


with st.sidebar:
    st.text_input("Backend URL", key="api_base")
    if st.session_state.user:
        st.success(f"Signed in as {st.session_state.user['username']}")
        if st.button("Log out"):
            api("POST", "/api/auth/logout")
            st.session_state.user = None
            st.rerun()

if not st.session_state.user:
    login_tab, register_tab = st.tabs(["Login", "Register"])
    with login_tab:
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
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
            new_username = st.text_input("New username")
            new_password = st.text_input("New password", type="password")
            if st.form_submit_button("Create account"):
                created = api(
                    "POST",
                    "/api/users/",
                    json={"username": new_username, "password": new_password},
                )
                if created:
                    st.success("Account created. You can now log in.")
    st.stop()

problems = api("GET", "/api/problems/") or []
if not problems:
    st.info("No problems have been added yet.")
    st.stop()

problem_ids = [problem["id"] for problem in problems]
selected_id = st.selectbox("Problem", problem_ids)
problem = api("GET", f"/api/problems/{selected_id}")
if problem:
    st.header(problem["title"])
    st.write(problem["description"])
    st.subheader("Input")
    st.write(problem["input_description"])
    st.subheader("Output")
    st.write(problem["output_description"])
    if problem.get("samples"):
        st.subheader("Sample")
        for index, sample in enumerate(problem["samples"], start=1):
            left, right = st.columns(2)
            with left:
                st.caption(f"Input {index}")
                st.code(sample["input"], language="text")
            with right:
                st.caption(f"Output {index}")
                st.code(sample["output"], language="text")

languages = api("GET", "/api/languages/") or {"name": ["python"]}
language = st.selectbox("Language", languages.get("name", ["python"]))
code = st.text_area("Code", height=320, placeholder="Write your solution here...")

if st.button("Submit", type="primary", disabled=not code.strip()):
    result = api(
        "POST",
        "/api/submissions/",
        json={"problem_id": selected_id, "language": language, "code": code},
    )
    if result:
        submission_id = result["submission_id"]
        st.session_state.last_submission_id = submission_id
        with st.status("Judging...", expanded=True) as status_box:
            for _ in range(100):
                detail = api("GET", f"/api/submissions/{submission_id}")
                if detail and "score" in detail:
                    status_box.update(label="Finished", state="complete")
                    st.metric("Score", f"{detail['score']} / {detail['counts']}")
                    break
                if detail and detail.get("status") == "error":
                    status_box.update(label="Judge error", state="error")
                    break
                time.sleep(0.1)
            else:
                status_box.update(label="Still pending", state="running")

st.divider()
st.subheader("Submission history")
history = api(
    "GET",
    f"/api/submissions/?user_id={st.session_state.user['user_id']}",
)
if history and history.get("submissions"):
    st.dataframe(history["submissions"], use_container_width=True, hide_index=True)
else:
    st.caption("No submissions yet.")

default_submission = st.session_state.last_submission_id or ""
lookup_id = st.text_input("Submission ID", value=default_submission)
if st.button("Refresh result", disabled=not lookup_id.strip()):
    detail = api("GET", f"/api/submissions/{lookup_id.strip()}")
    if detail:
        if "score" in detail:
            st.metric("Result", f"{detail['score']} / {detail['counts']}")
        else:
            st.info(f"Status: {detail['status']}")

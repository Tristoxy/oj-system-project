"""Restart persistence and unfinished-task recovery tests."""

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


# 函数 `admin_login`：负责当前测试或测试夹具。
def admin_login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admintestpassword"},
    )
    assert response.status_code == 200


# 函数 `test_problem_and_password_survive_restart`：负责当前测试或测试夹具。
def test_problem_and_password_survive_restart(
    tmp_path: Path,
    problem_payload: dict[str, object],
) -> None:
    data_dir = tmp_path / "persistent-data"
    with TestClient(create_app(data_dir)) as first:
        admin_login(first)
        assert first.post("/api/problems/", json=problem_payload).status_code == 200

    with TestClient(create_app(data_dir)) as second:
        admin_login(second)
        problems = second.get("/api/problems/").json()["data"]
        assert problems == [{"id": "sum_2", "title": "Two Sum"}]


# 函数 `test_pending_submission_resumes_after_restart`：负责当前测试或测试夹具。
def test_pending_submission_resumes_after_restart(tmp_path: Path) -> None:
    data_dir = tmp_path / "recover-data"
    problem = {
        "id": "spin",
        "title": "Spin",
        "description": "Never finish.",
        "input_description": "",
        "output_description": "",
        "samples": [],
        "constraints": "",
        "testcases": [{"input": "", "output": ""}],
        "time_limit": 0.1,
    }
    with TestClient(create_app(data_dir)) as first:
        admin_login(first)
        first.post("/api/problems/", json=problem)
        response = first.post(
            "/api/submissions/",
            json={"problem_id": "spin", "language": "python", "code": "while True: pass"},
        )
        submission_id = response.json()["data"]["submission_id"]

    with TestClient(create_app(data_dir)) as second:
        admin_login(second)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = second.get(f"/api/submissions/{submission_id}").json()["data"]
            if "score" in result:
                break
            time.sleep(0.02)
        assert {"score": result["score"], "counts": result["counts"]} == {
            "score": 0,
            "counts": 10,
        }
        log = second.get(f"/api/submissions/{submission_id}/log").json()["data"]
        assert log["details"][0]["result"] == "TLE"

"""End-to-end tests for Python/C++ judging and submission queries."""

import time

from fastapi.testclient import TestClient


def wait_for_result(client: TestClient, submission_id: str, timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/submissions/{submission_id}")
        data = response.json()["data"]
        if "score" in data or data.get("status") == "error":
            return data
        time.sleep(0.02)
    raise AssertionError("submission did not finish")


def add_problem(client: TestClient, payload: dict[str, object]) -> None:
    assert client.post("/api/problems/", json=payload).status_code == 200


def test_python_ac_and_wa(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    add_problem(admin_client, problem_payload)
    accepted = admin_client.post(
        "/api/submissions/",
        json={
            "problem_id": "sum_2",
            "language": "python",
            "code": "a, b = map(int, input().split())\nprint(a + b)",
        },
    )
    assert accepted.json()["data"]["status"] == "pending"
    accepted_id = accepted.json()["data"]["submission_id"]
    assert wait_for_result(admin_client, accepted_id) == {"score": 10, "counts": 10}

    wrong = admin_client.post(
        "/api/submissions/",
        json={"problem_id": "sum_2", "language": "python", "code": "print(0)"},
    )
    wrong_id = wrong.json()["data"]["submission_id"]
    assert wait_for_result(admin_client, wrong_id) == {"score": 0, "counts": 10}

    log = admin_client.get(f"/api/submissions/{accepted_id}/log").json()["data"]
    assert log["details"][0]["result"] == "AC"


def test_cpp_judging(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    add_problem(admin_client, problem_payload)
    response = admin_client.post(
        "/api/submissions/",
        json={
            "problem_id": "sum_2",
            "language": "cpp",
            "code": "#include <iostream>\nint main(){long long a,b;std::cin>>a>>b;std::cout<<a+b;}",
        },
    )
    submission_id = response.json()["data"]["submission_id"]
    assert wait_for_result(admin_client, submission_id, timeout=20) == {
        "score": 10,
        "counts": 10,
    }


def test_submission_list_requires_primary_filter(admin_client: TestClient) -> None:
    response = admin_client.get("/api/submissions/")
    assert response.status_code == 400


def test_time_limit_is_reported_in_log(admin_client: TestClient) -> None:
    payload = {
        "id": "spin",
        "title": "Spin",
        "description": "Never finish.",
        "input_description": "None.",
        "output_description": "None.",
        "samples": [{"input": "", "output": ""}],
        "constraints": "",
        "testcases": [{"input": "", "output": ""}],
        "time_limit": 0.05,
        "memory_limit": 128,
    }
    add_problem(admin_client, payload)
    response = admin_client.post(
        "/api/submissions/",
        json={"problem_id": "spin", "language": "python", "code": "while True: pass"},
    )
    submission_id = response.json()["data"]["submission_id"]

    assert wait_for_result(admin_client, submission_id)["score"] == 0
    detail = admin_client.get(f"/api/submissions/{submission_id}/log").json()["data"]
    assert detail["details"][0]["result"] == "TLE"

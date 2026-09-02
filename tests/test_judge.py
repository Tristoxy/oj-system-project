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


def test_runtime_compile_and_memory_failures_are_case_results(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    problem_payload["memory_limit"] = 64
    add_problem(admin_client, problem_payload)
    submissions = [
        ("python", "raise RuntimeError('boom')", "RE"),
        ("python", "x = bytearray(256 * 1024 * 1024)\nprint(3)", "MLE"),
        ("cpp", "this is not valid C++", "CE"),
    ]

    for language, code, expected in submissions:
        response = admin_client.post(
            "/api/submissions/",
            json={"problem_id": "sum_2", "language": language, "code": code},
        )
        submission_id = response.json()["data"]["submission_id"]
        assert wait_for_result(admin_client, submission_id)["score"] == 0
        log = admin_client.get(f"/api/submissions/{submission_id}/log").json()["data"]
        assert log["details"][0]["result"] == expected


def test_submission_rate_limit_precedes_missing_resource(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    add_problem(admin_client, problem_payload)
    payload = {"problem_id": "sum_2", "language": "python", "code": "print(3)"}
    for _ in range(3):
        assert admin_client.post("/api/submissions/", json=payload).status_code == 200

    response = admin_client.post(
        "/api/submissions/",
        json={"problem_id": "missing", "language": "python", "code": "print(3)"},
    )

    assert response.status_code == 429
    assert response.json()["code"] == 429


def test_submission_filters_pagination_and_rejudge(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    add_problem(admin_client, problem_payload)
    ids = []
    for code in ("print(3)", "print(0)"):
        response = admin_client.post(
            "/api/submissions/",
            json={"problem_id": "sum_2", "language": "python", "code": code},
        )
        submission_id = response.json()["data"]["submission_id"]
        ids.append(submission_id)
        wait_for_result(admin_client, submission_id)

    first_page = admin_client.get("/api/submissions/?problem_id=sum_2&page_size=1")
    assert first_page.status_code == 200
    assert first_page.json()["data"]["total"] == 2
    assert len(first_page.json()["data"]["submissions"]) == 1
    assert admin_client.get("/api/submissions/?problem_id=sum_2&page=1").status_code == 400

    response = admin_client.put(f"/api/submissions/{ids[1]}/rejudge")
    assert response.json()["data"] == {"submission_id": ids[1], "status": "pending"}
    assert wait_for_result(admin_client, ids[1]) == {"score": 0, "counts": 10}


def test_user_statistics_count_unique_solved_problems(admin_client: TestClient) -> None:
    for problem_id in ("one", "two"):
        payload = {
            "id": problem_id,
            "title": problem_id,
            "description": "Print 3.",
            "input_description": "",
            "output_description": "",
            "samples": [],
            "constraints": "",
            "testcases": [{"input": "", "output": "3"}],
        }
        add_problem(admin_client, payload)

    for problem_id in ("one", "one", "two"):
        response = admin_client.post(
            "/api/submissions/",
            json={"problem_id": problem_id, "language": "python", "code": "print(3)"},
        )
        wait_for_result(admin_client, response.json()["data"]["submission_id"])

    user = admin_client.get("/api/users/1").json()["data"]
    assert user["submit_count"] == 3
    assert user["resolve_count"] == 2

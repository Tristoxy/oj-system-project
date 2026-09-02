"""PDG normalization and plagiarism endpoint tests."""

import time

from fastapi.testclient import TestClient

from app.plagiarism.pdg import build_pdg, graph_similarity


def test_renamed_python_programs_are_similar() -> None:
    first = build_pdg("a = int(input())\nprint(a + 1)", "python")
    second = build_pdg("value = int(input())\nprint(value + 9)", "python")
    assert graph_similarity(first, second) >= 0.8


def test_plagiarism_task(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    admin_client.post("/api/problems/", json=problem_payload)
    for code in (
        "a,b=map(int,input().split())\nprint(a+b)",
        "x,y=map(int,input().split())\nprint(x+y)",
    ):
        admin_client.post(
            "/api/submissions/",
            json={"problem_id": "sum_2", "language": "python", "code": code},
        )
    started = admin_client.post(
        "/api/plagiarism/",
        json={"problem_id": "sum_2", "threshold": 0.7},
    )
    task_id = started.json()["data"]["task_id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = admin_client.get(f"/api/plagiarism/{task_id}").json()["data"]
        if result["status"] != "pending":
            break
        time.sleep(0.02)
    assert result["status"] == "success"
    assert result["submission_count"] == 2
    assert result["pair_count"] == 1
    assert result["clone_count"] == 1
    assert result["matches"][0]["is_clone"] is True
    assert result["matches"][0]["node_mapping"]
    report = admin_client.get(f"/api/plagiarism/{task_id}/report")
    assert report.status_code == 200
    assert report.json()["summary"]["clone_count"] == 1


def test_plagiarism_endpoints_require_admin(
    client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    client.post(
        "/api/users/",
        json={"username": "alice", "password": "secret1"},
    )
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret1"},
    )

    response = client.post(
        "/api/plagiarism/",
        json={"problem_id": str(problem_payload["id"]), "threshold": 0.8},
    )

    assert response.status_code == 403
    assert response.json()["code"] == 403

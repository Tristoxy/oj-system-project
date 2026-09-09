"""PDG normalization and plagiarism endpoint tests."""

import time

from fastapi.testclient import TestClient

from app.plagiarism.pdg import build_pdg, graph_similarity


# 函数 `test_renamed_python_programs_are_similar`：负责当前测试或测试夹具。
def test_renamed_python_programs_are_similar() -> None:
    first = build_pdg("a = int(input())\nprint(a + 1)", "python")
    second = build_pdg("value = int(input())\nprint(value + 9)", "python")
    assert graph_similarity(first, second) >= 0.8


# 函数 `test_cfg_models_if_branches_and_reaching_definitions`：负责当前测试或测试夹具。
def test_cfg_models_if_branches_and_reaching_definitions() -> None:
    graph = build_pdg(
        "if flag:\n    value = 1\nelse:\n    value = 2\nprint(value)",
        "python",
    )
    lines = {node["id"]: node["line"] for node in graph["nodes"]}
    edges = {
        (lines[edge["from"]], lines[edge["to"]], edge["type"])
        for edge in graph["edges"]
    }

    assert (1, 2, "flow") in edges
    assert (1, 4, "flow") in edges
    assert (2, 4, "flow") not in edges
    assert (2, 5, "flow") in edges
    assert (4, 5, "flow") in edges
    assert (2, 5, "data") in edges
    assert (4, 5, "data") in edges


# 函数 `test_cfg_contains_loop_back_edge`：负责当前测试或测试夹具。
def test_cfg_contains_loop_back_edge() -> None:
    graph = build_pdg(
        "while ready:\n    ready = update()\nprint(ready)",
        "python",
    )
    lines = {node["id"]: node["line"] for node in graph["nodes"]}
    flow_edges = {
        (lines[edge["from"]], lines[edge["to"]])
        for edge in graph["edges"]
        if edge["type"] == "flow"
    }

    assert (1, 2) in flow_edges
    assert (2, 1) in flow_edges
    assert (1, 3) in flow_edges


# 函数 `test_plagiarism_task`：负责当前测试或测试夹具。
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


# 函数 `test_plagiarism_endpoints_require_admin`：负责当前测试或测试夹具。
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

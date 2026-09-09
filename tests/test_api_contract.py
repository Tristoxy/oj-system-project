"""Cross-cutting tests for validation, permissions, and error precedence."""

from fastapi.testclient import TestClient


# 函数 `test_unauthenticated_error_precedes_invalid_query`：负责当前测试或测试夹具。
def test_unauthenticated_error_precedes_invalid_query(client: TestClient) -> None:
    response = client.get("/api/submissions/?page=not-an-integer")

    assert response.status_code == 401
    assert response.json() == {"code": 401, "msg": "not logged in", "data": None}


# 函数 `test_permission_error_precedes_secondary_filter_validation`：负责当前测试或测试夹具。
def test_permission_error_precedes_secondary_filter_validation(client: TestClient) -> None:
    alice = client.post(
        "/api/users/",
        json={"username": "alice", "password": "secret1"},
    ).json()["data"]
    bobby = client.post(
        "/api/users/",
        json={"username": "bobby", "password": "secret2"},
    ).json()["data"]
    assert alice["user_id"] != bobby["user_id"]
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret1"},
    )

    response = client.get(
        f"/api/submissions/?user_id={bobby['user_id']}&status=invalid"
    )

    assert response.status_code == 403
    assert response.json()["code"] == 403


# 函数 `test_nested_extra_problem_field_is_rejected`：负责当前测试或测试夹具。
def test_nested_extra_problem_field_is_rejected(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    problem_payload["samples"] = [{"input": "1 2", "output": "3", "secret": True}]

    response = admin_client.post("/api/problems/", json=problem_payload)

    assert response.status_code == 400
    assert response.json()["data"] is None


# 函数 `test_language_command_requires_placeholder`：负责当前测试或测试夹具。
def test_language_command_requires_placeholder(admin_client: TestClient) -> None:
    no_source = admin_client.post(
        "/api/languages/",
        json={"name": "bad", "file_ext": ".py", "run_cmd": "python3"},
    )
    broken_template = admin_client.post(
        "/api/languages/",
        json={"name": "broken", "file_ext": ".py", "run_cmd": "python3 {src"},
    )

    assert no_source.status_code == 400
    assert broken_template.status_code == 400

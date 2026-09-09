"""API tests for problem management and authorization."""

from fastapi.testclient import TestClient


# 函数 `test_problem_management_flow`：负责当前测试或测试夹具。
def test_problem_management_flow(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    create_response = admin_client.post("/api/problems/", json=problem_payload)
    assert create_response.status_code == 200
    assert create_response.json() == {
        "code": 200,
        "msg": "add success",
        "data": {"id": "sum_2"},
    }
    list_response = admin_client.get("/api/problems/")
    assert list_response.status_code == 200
    assert list_response.json()["data"] == [{"id": "sum_2", "title": "Two Sum"}]

    detail_response = admin_client.get("/api/problems/sum_2")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["id"] == "sum_2"
    assert detail["hint"] == ""
    assert detail["tags"] == []
    # 未填写的题目限制保持为空，判题时依次从所选语言和系统默认配置中解析。
    assert detail["time_limit"] is None
    assert detail["memory_limit"] is None

    delete_response = admin_client.delete("/api/problems/sum_2")
    assert delete_response.status_code == 200
    assert delete_response.json()["msg"] == "delete success"
    missing_response = admin_client.get("/api/problems/sum_2")
    assert missing_response.status_code == 404
    assert missing_response.json() == {
        "code": 404,
        "msg": "problem not found",
        "data": None,
    }


# 函数 `test_duplicate_problem_id_returns_409`：负责当前测试或测试夹具。
def test_duplicate_problem_id_returns_409(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    assert admin_client.post("/api/problems/", json=problem_payload).status_code == 200

    response = admin_client.post("/api/problems/", json=problem_payload)

    assert response.status_code == 409
    assert response.json()["code"] == 409


# 函数 `test_invalid_problem_returns_400`：负责当前测试或测试夹具。
def test_invalid_problem_returns_400(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/problems/",
        json={"id": "../unsafe", "title": "Incomplete problem"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400


# 函数 `test_delete_missing_problem_returns_404`：负责当前测试或测试夹具。
def test_delete_missing_problem_returns_404(admin_client: TestClient) -> None:
    response = admin_client.delete("/api/problems/not_found")

    assert response.status_code == 404
    assert response.json()["code"] == 404


# 函数 `test_authentication_precedes_body_validation`：负责当前测试或测试夹具。
def test_authentication_precedes_body_validation(client: TestClient) -> None:
    response = client.post("/api/problems/", json={})

    assert response.status_code == 401
    assert response.json()["code"] == 401

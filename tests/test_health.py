"""Tests for the application's health endpoint."""

from fastapi.testclient import TestClient

from app.main import create_app


# 函数 `test_health_check`：负责当前测试或测试夹具。
def test_health_check() -> None:
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "msg": "success",
        "data": {"status": "ok"},
    }


# 函数 `test_framework_errors_use_course_response_format`：负责当前测试或测试夹具。
def test_framework_errors_use_course_response_format() -> None:
    client = TestClient(create_app())

    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"code": 404, "msg": "Not Found", "data": None}

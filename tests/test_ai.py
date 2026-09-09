"""API tests for the 2026 AI-assisted problem authoring module."""

import asyncio
import json
import time
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


GENERATED_PROBLEM = {
    "id": "binary_search",
    "title": "Binary Search",
    "description": "Find the target in a sorted sequence.",
    "input_description": "A sorted sequence and a target.",
    "output_description": "The target index, or -1.",
    "samples": [{"input": "3 2\n1 2 3", "output": "1"}],
    "constraints": "1 <= n <= 100000",
    "testcases": [
        {"input": "1 1\n1", "output": "0"},
        {"input": "1 2\n1", "output": "-1"},
        {"input": "3 1\n1 2 3", "output": "0"},
        {"input": "3 3\n1 2 3", "output": "2"},
        {"input": "5 4\n1 2 3 4 5", "output": "3"},
        {"input": "4 9\n2 4 6 8", "output": "-1"},
    ],
    "hint": "Use two pointers for the search interval.",
    "source": "AI generated",
    "tags": ["binary search"],
    "time_limit": 1.0,
    "memory_limit": 128,
    "author": "AI assistant",
    "difficulty": "medium",
}


# 函数 `configure`：负责当前测试或测试夹具。
def configure(client: TestClient) -> dict:
    response = client.put(
        "/api/ai/model-config",
        json={
            "provider_url": "https://models.example/v1",
            "model": "course-model",
            "api_key": "secret-key-not-for-responses",
            "input_price": 1,
            "output_price": 2,
            "price_unit": 1_000_000,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


# 函数 `wait_for_ai`：负责当前测试或测试夹具。
def wait_for_ai(client: TestClient, task_id: str) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = client.get(f"/api/ai/problem-tasks/{task_id}").json()["data"]
        if result["status"] not in {"pending", "running"}:
            return result
        time.sleep(0.01)
    raise AssertionError("AI task did not finish")


# 函数 `test_ai_config_generation_usage_and_result_workflow`：负责当前测试或测试夹具。
def test_ai_config_generation_usage_and_result_workflow(admin_client: TestClient) -> None:
    public_config = configure(admin_client)
    assert public_config["api_key_configured"] is True
    assert "api_key" not in public_config

    service = admin_client.app.state.container.ai
    service._request_model = AsyncMock(
        return_value={
            "choices": [{"message": {"content": json.dumps(GENERATED_PROBLEM)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
    )
    created = admin_client.post(
        "/api/ai/problem-tasks/", json={"requirement": "Create a binary search problem"}
    )
    assert created.status_code == 200
    task_id = created.json()["data"]["task_id"]
    result = wait_for_ai(admin_client, task_id)
    assert result["status"] == "success"
    assert result["result"]["id"] == "binary_search"
    assert result["usage"] == {
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "cost": 0.0002,
        "currency": "USD",
    }
    assert "api_key" not in str(result)


# 函数 `test_ai_cancel_really_stops_task_and_enforces_owner`：负责当前测试或测试夹具。
def test_ai_cancel_really_stops_task_and_enforces_owner(
    admin_client: TestClient,
) -> None:
    configure(admin_client)
    gate = asyncio.Event()

    # 函数 `wait_forever`：负责当前测试或测试夹具。
    async def wait_forever(*args, **kwargs):
        del args, kwargs
        await gate.wait()

    admin_client.app.state.container.ai._request_model = wait_forever
    created = admin_client.post(
        "/api/ai/problem-tasks/", json={"requirement": "Make a loop problem"}
    ).json()["data"]

    admin_client.post("/api/users/", json={"username": "alice", "password": "secret1"})
    admin_client.post("/api/auth/logout")
    admin_client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    assert admin_client.get(f"/api/ai/problem-tasks/{created['task_id']}").status_code == 403

    admin_client.post("/api/auth/logout")
    admin_client.post(
        "/api/auth/login",
        json={"username": "Tristoxy", "password": "Qtc521521"},
    )

    cancelled = admin_client.put(f"/api/ai/problem-tasks/{created['task_id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"
    status = admin_client.get(f"/api/ai/problem-tasks/{created['task_id']}").json()["data"]
    assert status["status"] == "cancelled"


# 函数 `test_ai_config_is_required_and_key_is_never_returned`：负责当前测试或测试夹具。
def test_ai_config_is_required_and_key_is_never_returned(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/ai/problem-tasks/", json={"requirement": "Make a loop problem"}
    )
    assert response.status_code == 400
    assert admin_client.get("/api/ai/model-config").json()["data"] == {
        "api_key_configured": False
    }


# 函数 `test_reset_discards_runtime_model_key`：负责当前测试或测试夹具。
def test_reset_discards_runtime_model_key(admin_client: TestClient) -> None:
    configure(admin_client)
    assert admin_client.post("/api/reset/").status_code == 200
    admin_client.post(
        "/api/auth/login",
        json={"username": "Tristoxy", "password": "Qtc521521"},
    )
    assert admin_client.get("/api/ai/model-config").json()["data"] == {
        "api_key_configured": False
    }


# 函数 `test_malformed_model_response_becomes_terminal_error`：负责当前测试或测试夹具。
def test_malformed_model_response_becomes_terminal_error(admin_client: TestClient) -> None:
    configure(admin_client)
    admin_client.app.state.container.ai._request_model = AsyncMock(return_value={})
    created = admin_client.post(
        "/api/ai/problem-tasks/", json={"requirement": "Make an array problem"}
    ).json()["data"]
    result = wait_for_ai(admin_client, created["task_id"])
    assert result["status"] == "error"
    assert result["error"] == "模型请求或返回格式无效，请检查配置后重试"

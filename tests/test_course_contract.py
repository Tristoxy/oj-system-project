"""Black-box checks derived directly from the published course API contract."""

from fastapi.testclient import TestClient


def _register(client: TestClient, username: str) -> dict[str, object]:
    response = client.post(
        "/api/users/",
        json={"username": username, "password": "secret1"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_non_admin_permission_matrix(
    client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    alice = _register(client, "alice")
    bobby = _register(client, "bobby")
    assert client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret1"},
    ).status_code == 200

    # The course explicitly allows every logged-in user to add problems and
    # languages, while destructive and administrative actions remain admin-only.
    assert client.post("/api/problems/", json=problem_payload).status_code == 200
    assert client.post(
        "/api/languages/",
        json={
            "name": "python_copy",
            "file_ext": ".py",
            "run_cmd": "python3 {src}",
        },
    ).status_code == 200
    protected = (
        client.delete("/api/problems/sum_2"),
        client.put("/api/problems/sum_2/log_visibility", json={}),
        client.get("/api/users/"),
        client.put(f"/api/users/{alice['user_id']}/role", json={"role": "admin"}),
        client.post("/api/reset/"),
        client.get("/api/export/"),
        client.post("/api/plagiarism/", json={"problem_id": "sum_2"}),
    )
    assert all(response.status_code == 403 for response in protected)
    assert client.get(f"/api/users/{bobby['user_id']}").status_code == 403


def test_error_responses_always_match_http_status(client: TestClient) -> None:
    responses = (
        client.get("/api/problems/"),
        client.post("/api/problems/", json={}),
        client.post("/api/users/", json={}),
        client.get("/api/not-a-real-endpoint"),
    )

    for response in responses:
        payload = response.json()
        assert set(payload) == {"code", "msg", "data"}
        assert payload["code"] == response.status_code
        assert payload["data"] is None


def test_user_pagination_contract(admin_client: TestClient) -> None:
    _register(admin_client, "alice")
    _register(admin_client, "bobby")

    first = admin_client.get("/api/users/?page_size=1").json()["data"]
    second = admin_client.get("/api/users/?page=2&page_size=1").json()["data"]
    assert first["total"] == 3
    assert len(first["users"]) == 1
    assert first["users"][0]["user_id"] != second["users"][0]["user_id"]
    assert admin_client.get("/api/users/?page=1").status_code == 400
    assert admin_client.get("/api/users/?page_size=0").status_code == 400


def test_problem_resource_limits_are_bounded(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    problem_payload["time_limit"] = 61
    assert admin_client.post("/api/problems/", json=problem_payload).status_code == 400

    problem_payload["time_limit"] = 1
    problem_payload["memory_limit"] = 4097
    assert admin_client.post("/api/problems/", json=problem_payload).status_code == 400

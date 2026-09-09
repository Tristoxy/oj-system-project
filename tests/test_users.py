"""User, session, role, and permission tests."""

from fastapi.testclient import TestClient


# 函数 `test_register_login_logout`：负责当前测试或测试夹具。
def test_register_login_logout(client: TestClient) -> None:
    registered = client.post(
        "/api/users/",
        json={"username": "alice", "password": "secret1"},
    )
    assert registered.status_code == 200
    assert "password" not in registered.json()["data"]

    login = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret1"},
    )
    assert login.status_code == 200
    user_id = login.json()["data"]["user_id"]
    assert client.get(f"/api/users/{user_id}").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get(f"/api/users/{user_id}").status_code == 401


# 函数 `test_admin_can_ban_user`：负责当前测试或测试夹具。
def test_admin_can_ban_user(admin_client: TestClient) -> None:
    registered = admin_client.post(
        "/api/users/",
        json={"username": "blocked", "password": "secret1"},
    )
    user_id = registered.json()["data"]["user_id"]
    response = admin_client.put(f"/api/users/{user_id}/role", json={"role": "banned"})
    assert response.status_code == 200

    admin_client.post("/api/auth/logout")
    denied = admin_client.post(
        "/api/auth/login",
        json={"username": "blocked", "password": "secret1"},
    )
    assert denied.status_code == 403


# 函数 `test_last_admin_cannot_be_demoted`：保证系统不会因误操作失去全部管理员。
def test_last_admin_cannot_be_demoted(admin_client: TestClient) -> None:
    users = admin_client.get("/api/users/").json()["data"]["users"]
    admin = next(user for user in users if user["role"] == "admin")

    response = admin_client.put(
        f"/api/users/{admin['user_id']}/role", json={"role": "user"}
    )

    assert response.status_code == 400
    assert admin_client.get("/api/users/").status_code == 200


# 函数 `test_user_cannot_read_another_user`：负责当前测试或测试夹具。
def test_user_cannot_read_another_user(client: TestClient) -> None:
    first = client.post("/api/users/", json={"username": "alice", "password": "secret1"})
    second = client.post("/api/users/", json={"username": "bobby", "password": "secret2"})
    client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})

    response = client.get(f"/api/users/{second.json()['data']['user_id']}")
    assert first.status_code == 200
    assert response.status_code == 403


# 函数 `test_banned_user_with_existing_session_gets_403`：负责当前测试或测试夹具。
def test_banned_user_with_existing_session_gets_403(client: TestClient) -> None:
    registered = client.post(
        "/api/users/",
        json={"username": "charlie", "password": "secret3"},
    )
    user_id = registered.json()["data"]["user_id"]
    client.post(
        "/api/auth/login",
        json={"username": "charlie", "password": "secret3"},
    )
    user_session = client.cookies.get("oj_session")

    client.post(
        "/api/auth/login",
        json={"username": "Tristoxy", "password": "Qtc521521"},
    )
    assert client.put(f"/api/users/{user_id}/role", json={"role": "banned"}).status_code == 200

    client.cookies.set("oj_session", user_session)
    response = client.get("/api/problems/")
    assert response.status_code == 403
    assert response.json()["code"] == 403

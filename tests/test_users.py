"""User, session, role, and permission tests."""

from fastapi.testclient import TestClient


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


def test_user_cannot_read_another_user(client: TestClient) -> None:
    first = client.post("/api/users/", json={"username": "alice", "password": "secret1"})
    second = client.post("/api/users/", json={"username": "bobby", "password": "secret2"})
    client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})

    response = client.get(f"/api/users/{second.json()['data']['user_id']}")
    assert first.status_code == 200
    assert response.status_code == 403

"""Persistence, export/import, and reset tests."""

import json

from fastapi.testclient import TestClient


def test_export_reset_and_import(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    admin_client.post("/api/problems/", json=problem_payload)
    exported = admin_client.get("/api/export/")
    assert exported.status_code == 200
    bundle = exported.json()["data"]
    assert bundle["users"][0]["password"].startswith("pbkdf2_sha256$")
    assert bundle["users"][0]["password"] != "admintestpassword"

    reset = admin_client.post("/api/reset/")
    assert reset.status_code == 200
    assert admin_client.get("/api/problems/").status_code == 401

    admin_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admintestpassword"},
    )
    imported = admin_client.post(
        "/api/import/",
        files={"file": ("backup.json", json.dumps(bundle), "application/json")},
    )
    assert imported.status_code == 200
    assert admin_client.get("/api/problems/").status_code == 401

    admin_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admintestpassword"},
    )
    assert len(admin_client.get("/api/problems/").json()["data"]) == 1


def test_import_rejects_malformed_password_hash(admin_client: TestClient) -> None:
    bundle = admin_client.get("/api/export/").json()["data"]
    bundle["users"][0]["password"] = "pbkdf2_sha256$999999999$bad$bad"

    response = admin_client.post(
        "/api/import/",
        files={"file": ("backup.json", json.dumps(bundle), "application/json")},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400

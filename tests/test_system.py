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


def test_invalid_import_does_not_change_state_or_session(
    admin_client: TestClient,
) -> None:
    bundle = admin_client.get("/api/export/").json()["data"]
    duplicate = dict(bundle["users"][0])
    duplicate["user_id"] = "2"
    bundle["users"].append(duplicate)

    response = admin_client.post(
        "/api/import/",
        files={"file": ("backup.json", json.dumps(bundle), "application/json")},
    )

    assert response.status_code == 400
    still_logged_in = admin_client.get("/api/export/")
    assert still_logged_in.status_code == 200
    assert len(still_logged_in.json()["data"]["users"]) == 1


def test_import_rejects_broken_submission_reference(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    admin_client.post("/api/problems/", json=problem_payload)
    bundle = admin_client.get("/api/export/").json()["data"]
    bundle["submissions"].append(
        {
            "submission_id": "1",
            "user_id": "missing-user",
            "problem_id": "sum_2",
            "language": "python",
            "code": "print(3)",
            "status": "pending",
            "details": [],
            "score": 0,
            "counts": 10,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )

    response = admin_client.post(
        "/api/import/",
        files={"file": ("backup.json", json.dumps(bundle), "application/json")},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400

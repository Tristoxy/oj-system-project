"""Persistence, export/import, and reset tests."""

import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api import system as system_api
from tests.test_judge import wait_for_result


# 函数 `test_export_reset_and_import`：负责当前测试或测试夹具。
def test_export_reset_and_import(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    admin_client.post("/api/problems/", json=problem_payload)
    exported = admin_client.get("/api/export/")
    assert exported.status_code == 200
    bundle = exported.json()["data"]
    assert bundle["users"][0]["password"].startswith("pbkdf2_sha256$")
    assert bundle["users"][0]["password"] != "Qtc521521"

    reset = admin_client.post("/api/reset/")
    assert reset.status_code == 200
    assert admin_client.get("/api/problems/").status_code == 401

    admin_client.post(
        "/api/auth/login",
        json={"username": "Tristoxy", "password": "Qtc521521"},
    )
    imported = admin_client.post(
        "/api/import/",
        files={"file": ("backup.json", json.dumps(bundle), "application/json")},
    )
    assert imported.status_code == 200
    assert admin_client.get("/api/problems/").status_code == 401

    admin_client.post(
        "/api/auth/login",
        json={"username": "Tristoxy", "password": "Qtc521521"},
    )
    assert len(admin_client.get("/api/problems/").json()["data"]) == 4


# 函数 `test_import_rejects_malformed_password_hash`：负责当前测试或测试夹具。
def test_import_rejects_malformed_password_hash(admin_client: TestClient) -> None:
    bundle = admin_client.get("/api/export/").json()["data"]
    bundle["users"][0]["password"] = "pbkdf2_sha256$999999999$bad$bad"

    response = admin_client.post(
        "/api/import/",
        files={"file": ("backup.json", json.dumps(bundle), "application/json")},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400


# 函数 `test_invalid_import_does_not_change_state_or_session`：负责当前测试或测试夹具。
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


# 函数 `test_import_rejects_broken_submission_reference`：负责当前测试或测试夹具。
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
            "counts": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )

    response = admin_client.post(
        "/api/import/",
        files={"file": ("backup.json", json.dumps(bundle), "application/json")},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400


# 函数 `test_export_matches_official_submission_shape_and_round_trips`：负责当前测试或测试夹具。
def test_export_matches_official_submission_shape_and_round_trips(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    admin_client.post("/api/problems/", json=problem_payload)
    submitted = admin_client.post(
        "/api/submissions/",
        json={"problem_id": "sum_2", "language": "python", "code": "print(3)"},
    ).json()["data"]
    wait_for_result(admin_client, submitted["submission_id"])

    bundle = admin_client.get("/api/export/").json()["data"]
    exported_submission = bundle["submissions"][0]
    assert set(exported_submission) == {
        "submission_id",
        "user_id",
        "problem_id",
        "language",
        "code",
        "status",
        "details",
        "score",
        "counts",
    }

    imported = admin_client.post(
        "/api/import/",
        files={"file": ("official-backup.json", json.dumps(bundle), "application/json")},
    )
    assert imported.status_code == 200

    admin_client.post(
        "/api/auth/login",
        json={"username": "Tristoxy", "password": "Qtc521521"},
    )
    restored = admin_client.get(
        f"/api/submissions/{submitted['submission_id']}"
    ).json()["data"]
    assert {"score": restored["score"], "counts": restored["counts"]} == {
        "score": 10,
        "counts": 1,
    }


# 函数 `test_import_size_limit_is_checked_before_json_parsing`：负责当前测试或测试夹具。
def test_import_size_limit_is_checked_before_json_parsing(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(system_api, "MAX_IMPORT_BYTES", 8)

    response = admin_client.post(
        "/api/import/",
        files={"file": ("large.json", b'{"long":1}', "application/json")},
    )

    assert response.status_code == 400
    assert response.json()["msg"] == "import file is too large"


# 函数 `test_user_listing_handles_mixed_imported_ids`：负责当前测试或测试夹具。
def test_user_listing_handles_mixed_imported_ids(admin_client: TestClient) -> None:
    bundle = admin_client.get("/api/export/").json()["data"]
    imported_user = dict(bundle["users"][0])
    imported_user.update(user_id="teacher", username="teacher")
    bundle["users"].append(imported_user)

    assert admin_client.post(
        "/api/import/",
        files={"file": ("users.json", json.dumps(bundle), "application/json")},
    ).status_code == 200
    admin_client.post(
        "/api/auth/login",
        json={"username": "Tristoxy", "password": "Qtc521521"},
    )

    users = admin_client.get("/api/users/")
    assert users.status_code == 200
    assert [item["user_id"] for item in users.json()["data"]["users"]] == [
        "1",
        "teacher",
    ]


# 函数 `test_import_resumes_all_background_workers`：负责当前测试或测试夹具。
def test_import_resumes_all_background_workers(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = admin_client.get("/api/export/").json()["data"]
    container = admin_client.app.state.container
    resume_submissions = AsyncMock()
    resume_plagiarism = AsyncMock()
    monkeypatch.setattr(container.submissions, "resume_pending", resume_submissions)
    monkeypatch.setattr(container.plagiarism, "resume_pending", resume_plagiarism)

    response = admin_client.post(
        "/api/import/",
        files={"file": ("backup.json", json.dumps(bundle), "application/json")},
    )

    assert response.status_code == 200
    resume_submissions.assert_awaited_once()
    resume_plagiarism.assert_awaited_once()


# 函数 `test_failed_import_after_pause_still_resumes_workers`：负责当前测试或测试夹具。
def test_failed_import_after_pause_still_resumes_workers(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = admin_client.get("/api/export/").json()["data"]
    container = admin_client.app.state.container
    resume_submissions = AsyncMock()
    resume_plagiarism = AsyncMock()
    monkeypatch.setattr(container.submissions, "resume_pending", resume_submissions)
    monkeypatch.setattr(container.plagiarism, "resume_pending", resume_plagiarism)
    monkeypatch.setattr(
        container.system,
        "import_data",
        AsyncMock(side_effect=RuntimeError("simulated storage failure")),
    )

    with pytest.raises(RuntimeError, match="simulated storage failure"):
        admin_client.post(
            "/api/import/",
            files={"file": ("backup.json", json.dumps(bundle), "application/json")},
        )

    resume_submissions.assert_awaited_once()
    resume_plagiarism.assert_awaited_once()


# 函数 `test_import_rejects_naive_submission_timestamp`：负责当前测试或测试夹具。
def test_import_rejects_naive_submission_timestamp(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    admin_client.post("/api/problems/", json=problem_payload)
    bundle = admin_client.get("/api/export/").json()["data"]
    bundle["submissions"].append(
        {
            "submission_id": "1",
            "user_id": "1",
            "problem_id": "sum_2",
            "language": "python",
            "code": "print(3)",
            "status": "success",
            "details": [{"id": 1, "result": "AC", "time": 0, "memory": 1}],
            "score": 10,
            "counts": 1,
            "created_at": "2026-01-01T00:00:00",
        }
    )

    response = admin_client.post(
        "/api/import/",
        files={"file": ("naive-time.json", json.dumps(bundle), "application/json")},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400

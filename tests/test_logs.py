"""Log visibility, result privacy, and audit tests."""

from fastapi.testclient import TestClient

from tests.test_judge import wait_for_result


# 函数 `login`：负责当前测试或测试夹具。
def login(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200


# 函数 `test_private_and_public_log_visibility_is_audited`：负责当前测试或测试夹具。
def test_private_and_public_log_visibility_is_audited(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    assert admin_client.post("/api/problems/", json=problem_payload).status_code == 200
    for username in ("alice", "bobby"):
        assert admin_client.post(
            "/api/users/",
            json={"username": username, "password": "secret1"},
        ).status_code == 200

    login(admin_client, "alice", "secret1")
    submission = admin_client.post(
        "/api/submissions/",
        json={"problem_id": "sum_2", "language": "python", "code": "print(3)"},
    ).json()["data"]
    submission_id = submission["submission_id"]
    wait_for_result(admin_client, submission_id)
    owner_log = admin_client.get(f"/api/submissions/{submission_id}/log")
    assert owner_log.status_code == 200
    assert "details" not in owner_log.json()["data"]

    login(admin_client, "bobby", "secret1")
    private_log = admin_client.get(f"/api/submissions/{submission_id}/log")
    assert private_log.status_code == 403

    login(admin_client, "Tristoxy", "Qtc521521")
    visibility = admin_client.put(
        "/api/problems/sum_2/log_visibility",
        json={"public_cases": True},
    )
    assert visibility.status_code == 200

    login(admin_client, "bobby", "secret1")
    public_log = admin_client.get(f"/api/submissions/{submission_id}/log")
    assert public_log.status_code == 200
    assert public_log.json()["data"]["details"][0]["result"] == "AC"
    assert admin_client.get(f"/api/submissions/{submission_id}").status_code == 403

    login(admin_client, "Tristoxy", "Qtc521521")
    audit = admin_client.get("/api/logs/access/?problem_id=sum_2")
    assert audit.status_code == 200
    records = audit.json()["data"]
    assert {record["status"] for record in records} == {"200", "403"}
    assert all(record["action"] == "view_logs" for record in records)

"""Special Judge configuration, safety, and execution tests."""

from fastapi.testclient import TestClient

from tests.test_judge import wait_for_result


def test_spj_upload_execution_and_delete(admin_client: TestClient) -> None:
    problem = {
        "id": "unordered",
        "title": "Unordered output",
        "description": "Print both values in any order.",
        "input_description": "",
        "output_description": "",
        "samples": [],
        "constraints": "",
        "testcases": [{"input": "", "output": "1 2"}],
    }
    admin_client.post("/api/problems/", json=problem)
    script = b"""import sys
with open(sys.argv[2], encoding='utf-8') as expected:
    expected_words = expected.read().split()
with open(sys.argv[3], encoding='utf-8') as actual:
    actual_words = actual.read().split()
raise SystemExit(0 if sorted(expected_words) == sorted(actual_words) else 1)
"""

    upload = admin_client.post(
        "/api/problems/unordered/spj",
        files={"file": ("judge.py", script, "text/x-python")},
    )
    assert upload.status_code == 200
    assert admin_client.get("/api/problems/unordered").json()["data"]["judge_mode"] == "spj"

    submitted = admin_client.post(
        "/api/submissions/",
        json={
            "problem_id": "unordered",
            "language": "python",
            "code": "print('2 1')",
        },
    )
    submission_id = submitted.json()["data"]["submission_id"]
    assert wait_for_result(admin_client, submission_id) == {"score": 10, "counts": 10}

    deleted = admin_client.delete("/api/problems/unordered/spj")
    assert deleted.status_code == 200
    assert admin_client.get("/api/problems/unordered").json()["data"]["judge_mode"] == "standard"


def test_spj_rejects_unsafe_script_and_wrong_extension(
    admin_client: TestClient,
    problem_payload: dict[str, object],
) -> None:
    admin_client.post("/api/problems/", json=problem_payload)

    unsafe = admin_client.post(
        "/api/problems/sum_2/spj",
        files={"file": ("judge.py", b"import os\nos.system('id')", "text/x-python")},
    )
    wrong_type = admin_client.post(
        "/api/problems/sum_2/spj",
        files={"file": ("judge.txt", b"raise SystemExit(0)", "text/plain")},
    )

    assert unsafe.status_code == 400
    assert wrong_type.status_code == 400

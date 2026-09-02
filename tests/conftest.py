"""Shared pytest fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(tmp_path / "data")) as test_client:
        yield test_client


@pytest.fixture
def admin_client(client: TestClient) -> TestClient:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admintestpassword"},
    )
    assert response.status_code == 200
    return client


@pytest.fixture
def problem_payload() -> dict[str, object]:
    return {
        "id": "sum_2",
        "title": "Two Sum",
        "description": "Read two integers and print their sum.",
        "input_description": "Two integers separated by a space.",
        "output_description": "The sum of the two integers.",
        "samples": [{"input": "1 2", "output": "3"}],
        "constraints": "-10^9 <= a, b <= 10^9",
        "testcases": [{"input": "1 2", "output": "3"}],
    }

from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import T0, clock_header

API = "/api/v1"


def create_member(client: TestClient, name: str = "Asha Rao", phone: str = "+919800011111") -> int:
    response = client.post(
        f"{API}/members", json={"name": name, "phone": phone}, headers=clock_header(T0)
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def create_item(client: TestClient, name: str = "Cordless drill", value: int = 450_000) -> int:
    response = client.post(
        f"{API}/items",
        json={"name": name, "category": "Power tools", "replacement_value_paise": value},
        headers=clock_header(T0),
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def post(client: TestClient, path: str, at: datetime = T0, json: Any = None):  # type: ignore[no-untyped-def]
    return client.post(f"{API}{path}", json=json, headers=clock_header(at))


def get(client: TestClient, path: str, at: datetime = T0, **params: Any):  # type: ignore[no-untyped-def]
    return client.get(f"{API}{path}", params=params, headers=clock_header(at))


def error_code(response) -> str:  # type: ignore[no-untyped-def]
    return str(response.json()["error"]["code"])

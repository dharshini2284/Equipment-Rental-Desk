"""Malformed input, the error envelope, the clock override, health and CORS."""

import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.persistence.models import Base
from tests.api.helpers import API, create_item, create_member, error_code


def assert_error_envelope(response, status: int, error_type: str) -> dict:  # type: ignore[no-untyped-def, type-arg]
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert set(error) == {"type", "code", "message", "details", "request_id"}
    assert error["type"] == error_type
    assert error["request_id"] == response.headers["X-Request-ID"]
    return error  # type: ignore[no-any-return]


class TestMalformedInput:
    def test_broken_json(self, client: TestClient) -> None:
        response = client.post(
            f"{API}/members", content=b"{not json", headers={"Content-Type": "application/json"}
        )
        assert_error_envelope(response, 400, "validation")

    def test_missing_fields(self, client: TestClient) -> None:
        error = assert_error_envelope(client.post(f"{API}/members", json={}), 400, "validation")
        fields = {f["field"] for f in error["details"]["fields"]}
        assert fields == {"body.name", "body.phone"}

    @pytest.mark.parametrize("amount", ["100", 100.5, True, 0, -500, 10**12, None])
    def test_bad_payment_amounts(self, client: TestClient, amount: object) -> None:
        member_id = create_member(client)
        response = client.post(f"{API}/members/{member_id}/payments", json={"amount_paise": amount})
        assert_error_envelope(response, 400, "validation")

    @pytest.mark.parametrize("value", [0, -1, "4500", 1.5, 10**10])
    def test_bad_replacement_values(self, client: TestClient, value: object) -> None:
        response = client.post(
            f"{API}/items",
            json={"name": "Drill", "category": "Tools", "replacement_value_paise": value},
        )
        assert_error_envelope(response, 400, "validation")

    @pytest.mark.parametrize("phone", ["12345", "abcdefghij", "+91 98000 1111 22222 3", ""])
    def test_bad_phone_numbers(self, client: TestClient, phone: str) -> None:
        response = client.post(f"{API}/members", json={"name": "A", "phone": phone})
        assert_error_envelope(response, 400, "validation")

    def test_overlong_name(self, client: TestClient) -> None:
        response = client.post(f"{API}/members", json={"name": "x" * 101, "phone": "+919800000000"})
        assert_error_envelope(response, 400, "validation")

    def test_unknown_field(self, client: TestClient) -> None:
        response = client.post(
            f"{API}/loans", json={"member_id": 1, "item_id": 1, "status": "checked_out"}
        )
        assert_error_envelope(response, 400, "validation")

    def test_string_ids_in_body(self, client: TestClient) -> None:
        response = client.post(f"{API}/loans", json={"member_id": "1", "item_id": "1"})
        assert_error_envelope(response, 400, "validation")

    @pytest.mark.parametrize(
        "path", ["/items/abc", "/items/0", "/items/-1", "/items/99999999999999999999"]
    )
    def test_bad_path_ids(self, client: TestClient, path: str) -> None:
        assert_error_envelope(client.get(f"{API}{path}"), 400, "validation")

    @pytest.mark.parametrize(
        "params",
        [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "lost"}, {"q": "x" * 101}],
    )
    def test_bad_list_params(self, client: TestClient, params: dict) -> None:  # type: ignore[type-arg]
        assert_error_envelope(client.get(f"{API}/items", params=params), 400, "validation")

    def test_return_body_with_wrong_type(self, client: TestClient) -> None:
        response = client.post(f"{API}/loans/1/return", json={"send_to_maintenance": "yes"})
        assert_error_envelope(response, 400, "validation")

    def test_sql_like_search_is_just_text(self, client: TestClient) -> None:
        create_item(client)
        response = client.get(f"{API}/items", params={"q": "'; DROP TABLE items; --"})
        assert response.status_code == 200
        assert response.json()["total"] == 0
        assert client.get(f"{API}/items").json()["total"] == 1

    def test_unknown_route_uses_envelope(self, client: TestClient) -> None:
        assert error_code(client.get(f"{API}/nope")) == "ROUTE_NOT_FOUND"

    def test_wrong_method_uses_envelope(self, client: TestClient) -> None:
        assert error_code(client.put(f"{API}/items")) == "METHOD_NOT_ALLOWED"


class TestTestClock:
    def test_clock_endpoint_reflects_header(self, client: TestClient) -> None:
        response = client.get(f"{API}/clock", headers={"X-Test-Clock": "2026-11-01T09:00:00+05:30"})
        body = response.json()
        assert body["now"] == "2026-11-01T03:30:00Z"
        assert body["test_clock_active"] is True
        assert response.headers["X-Effective-Clock"] == "2026-11-01T03:30:00+00:00"

    def test_without_header_uses_real_time(self, client: TestClient) -> None:
        assert client.get(f"{API}/clock").json()["test_clock_active"] is False

    @pytest.mark.parametrize("value", ["tomorrow", "2026-11-01T09:00:00", "2026-13-01T00:00:00Z"])
    def test_invalid_header_is_400(self, client: TestClient, value: str) -> None:
        response = client.get(f"{API}/clock", headers={"X-Test-Clock": value})
        error = assert_error_envelope(response, 400, "bad_request")
        assert error["code"] == "INVALID_TEST_CLOCK"

    def test_header_can_be_disabled(self, api_settings: Settings) -> None:
        settings = api_settings.model_copy(update={"allow_test_clock": False})
        app = create_app(settings)
        with TestClient(app) as locked_client:
            response = locked_client.get(
                f"{API}/clock", headers={"X-Test-Clock": "2026-11-01T09:00:00Z"}
            )
        assert error_code(response) == "TEST_CLOCK_DISABLED"
        app.state.engine.dispose()


class TestSystem:
    def test_health(self, client: TestClient) -> None:
        assert client.get("/health").json() == {"status": "ok", "database": "ok"}
        assert client.get(f"{API}/health").status_code == 200

    def test_health_reports_database_failure(self, client: TestClient) -> None:
        client.app.state.session_factory.configure(bind=_unreachable_engine())  # type: ignore[attr-defined]
        response = client.get("/health")
        assert response.status_code == 503

    def test_request_id_is_echoed_when_safe(self, client: TestClient) -> None:
        response = client.get("/health", headers={"X-Request-ID": "abc-123"})
        assert response.headers["X-Request-ID"] == "abc-123"
        unsafe = client.get("/health", headers={"X-Request-ID": "bad id with spaces"})
        assert unsafe.headers["X-Request-ID"] != "bad id with spaces"

    def test_cors_allows_configured_origin_only(self, client: TestClient) -> None:
        preflight = {
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Test-Clock, Content-Type",
        }
        allowed = client.options(
            f"{API}/loans", headers={"Origin": "http://localhost:5173", **preflight}
        )
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
        denied = client.options(
            f"{API}/loans", headers={"Origin": "https://evil.example", **preflight}
        )
        assert "access-control-allow-origin" not in denied.headers

    def test_openapi_documents_400_for_validation(self, client: TestClient) -> None:
        spec = client.get("/openapi.json").json()
        reserve = spec["paths"]["/api/v1/loans"]["post"]["responses"]
        assert "400" in reserve and "422" in reserve  # 422 here is the business-rule response
        assert "HTTPValidationError" not in str(reserve)


class TestUnexpectedErrors:
    def test_unhandled_exception_returns_500_without_trace(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app.services import items as item_service

        def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("secret internal detail")

        monkeypatch.setattr(item_service, "list_categories", explode)
        with caplog.at_level(logging.ERROR):
            response = client.get(f"{API}/items/categories")
        error = assert_error_envelope(response, 500, "internal")
        assert "secret" not in response.text
        assert error["code"] == "INTERNAL_ERROR"
        assert any("request.unhandled_exception" in r.message for r in caplog.records)

    def test_database_error_returns_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sqlalchemy.exc import OperationalError

        from app.services import items as item_service

        def locked(*args: object, **kwargs: object) -> None:
            raise OperationalError("SELECT 1", {}, Exception("database is locked"))

        monkeypatch.setattr(item_service, "list_categories", locked)
        assert_error_envelope(client.get(f"{API}/items/categories"), 503, "unavailable")

    def test_integrity_error_returns_409(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sqlalchemy.exc import IntegrityError

        from app.services import items as item_service

        def clash(*args: object, **kwargs: object) -> None:
            raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

        monkeypatch.setattr(item_service, "list_categories", clash)
        error = assert_error_envelope(client.get(f"{API}/items/categories"), 409, "conflict")
        assert error["code"] == "CONCURRENT_UPDATE"
        assert "UNIQUE" not in str(error)


def _unreachable_engine():  # type: ignore[no-untyped-def]
    from sqlalchemy import create_engine

    # SQLite cannot create a file inside a directory that does not exist.
    return create_engine("sqlite:///no/such/directory/rental.db")


def test_logs_are_json_with_request_id(
    api_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    app = create_app(api_settings.model_copy(update={"log_level": "INFO"}))
    Base.metadata.drop_all(app.state.engine)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as test_client:
        member_id = create_member(test_client)
        test_client.post(f"{API}/members/{member_id}/payments", json={"amount_paise": 500})
    app.state.engine.dispose()

    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    rejected = next(line for line in lines if line["event"] == "request.rejected")
    assert rejected["level"] == "WARNING"
    assert rejected["code"] == "PAYMENT_EXCEEDS_BALANCE"
    assert rejected["member_id"] == member_id
    assert rejected["request_id"]
    completed = [line for line in lines if line["event"] == "request.completed"]
    assert {line["status"] for line in completed} == {201, 422}

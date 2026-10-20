from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from tests.api.helpers import API, create_item, create_member, error_code, get, post
from tests.conftest import T0


def lend(client: TestClient, member_id: int, item_id: int) -> int:
    loan_id = post(client, "/loans", json={"member_id": member_id, "item_id": item_id}).json()["id"]
    assert post(client, f"/loans/{loan_id}/checkout").status_code == 200
    return int(loan_id)


def test_waitlist_round_trip(client: TestClient) -> None:
    item_id = create_item(client)
    loan_id = lend(client, create_member(client, "Holder", "+919800070001"), item_id)
    waiter = create_member(client, "Waiter", "+919800070002")

    joined = post(client, "/waitlist", json={"member_id": waiter, "item_id": item_id})
    assert joined.status_code == 201
    assert joined.json()["position"] == 1 and joined.json()["status"] == "waiting"

    again = post(client, "/waitlist", json={"member_id": waiter, "item_id": item_id})
    assert again.status_code == 409 and error_code(again) == "ALREADY_ON_WAITLIST"

    post(client, f"/loans/{loan_id}/return", T0 + timedelta(days=1))
    item = get(client, f"/items/{item_id}", T0 + timedelta(days=1)).json()
    assert item["status"] == "reserved" and item["current_loan"]["member_id"] == waiter

    entries = get(client, "/waitlist", item_id=item_id).json()["items"]
    assert (
        entries[0]["status"] == "fulfilled" and entries[0]["loan_id"] == item["current_loan"]["id"]
    )


def test_join_available_item_is_409(client: TestClient) -> None:
    response = post(
        client,
        "/waitlist",
        json={"member_id": create_member(client), "item_id": create_item(client)},
    )
    assert response.status_code == 409 and error_code(response) == "INVALID_TRANSITION"


def test_leave_waitlist(client: TestClient) -> None:
    item_id = create_item(client)
    lend(client, create_member(client, "Holder", "+919800070003"), item_id)
    entry = post(
        client,
        "/waitlist",
        json={"member_id": create_member(client, "W", "+919800070004"), "item_id": item_id},
    ).json()
    assert post(client, f"/waitlist/{entry['id']}/cancel").json()["status"] == "cancelled"
    assert post(client, f"/waitlist/{entry['id']}/cancel").status_code == 409
    assert post(client, "/waitlist/9999/cancel").status_code == 404


@pytest.mark.parametrize(
    "body", [{}, {"member_id": "1", "item_id": 1}, {"member_id": 1, "item_id": 0}, {"x": 1}]
)
def test_join_validation(client: TestClient, body: dict) -> None:  # type: ignore[type-arg]
    assert client.post(f"{API}/waitlist", json=body).status_code == 400


def test_outbox_lists_messages_newest_first(client: TestClient) -> None:
    member_id = create_member(client)
    lend(client, member_id, create_item(client))
    page = get(client, "/notifications", member_id=member_id).json()
    assert [n["kind"] for n in page["items"]] == ["checked_out", "reservation_created"]
    assert page["items"][0]["delivery"] == "stub"
    assert page["items"][0]["recipient"] == "+919800011111"
    assert get(client, "/notifications", kind="checked_out").json()["total"] == 1


def test_overdue_reminders_endpoint(client: TestClient) -> None:
    lend(client, create_member(client), create_item(client))
    late = T0 + timedelta(days=9)
    first = post(client, "/notifications/overdue-reminders", late).json()
    second = post(client, "/notifications/overdue-reminders", late).json()
    assert first == {"queued": 1, "skipped_recently_reminded": 0}
    assert second == {"queued": 0, "skipped_recently_reminded": 1}


def test_statement_pdf(client: TestClient) -> None:
    member_id = create_member(client)
    loan_id = lend(client, member_id, create_item(client))
    post(client, f"/loans/{loan_id}/return", T0 + timedelta(days=9))
    response = client.get(f"{API}/members/{member_id}/statement.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "statement-member-" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    assert b"Statement - Asha Rao" in response.content  # document title metadata


def test_statement_pdf_for_member_without_history(client: TestClient) -> None:
    response = client.get(f"{API}/members/{create_member(client)}/statement.pdf")
    assert response.status_code == 200 and response.content.startswith(b"%PDF")


def test_statement_pdf_unknown_member_is_json_404(client: TestClient) -> None:
    response = client.get(f"{API}/members/9999/statement.pdf")
    assert response.status_code == 404 and error_code(response) == "NOT_FOUND"


def test_member_on_waitlist_cannot_be_deleted(client: TestClient) -> None:
    item_id = create_item(client)
    lend(client, create_member(client, "Holder", "+919800070005"), item_id)
    waiter = create_member(client, "W", "+919800070006")
    post(client, "/waitlist", json={"member_id": waiter, "item_id": item_id})
    response = client.delete(f"{API}/members/{waiter}")
    assert response.status_code == 409 and error_code(response) == "MEMBER_HAS_HISTORY"

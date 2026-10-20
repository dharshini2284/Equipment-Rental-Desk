"""The edge cases listed in the problem statement, exercised over HTTP."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi.testclient import TestClient

from tests.api.helpers import create_item, create_member, error_code, get, post
from tests.conftest import T0


def reserve(client: TestClient, member_id: int, item_id: int, at=T0):  # type: ignore[no-untyped-def]
    return post(client, "/loans", at, json={"member_id": member_id, "item_id": item_id})


def checked_out_loan(client: TestClient, member_id: int, item_id: int) -> int:
    loan_id = reserve(client, member_id, item_id).json()["id"]
    assert post(client, f"/loans/{loan_id}/checkout").status_code == 200
    return int(loan_id)


def test_reserve_checkout_return_round_trip(client: TestClient) -> None:
    member_id, item_id = create_member(client), create_item(client)

    reserved = reserve(client, member_id, item_id)
    assert reserved.status_code == 201
    body = reserved.json()
    assert body["status"] == "reserved"
    assert body["reservation_expires_at"] == (T0 + timedelta(hours=48)).isoformat().replace(
        "+00:00", "Z"
    )

    loan_id = body["id"]
    checked_out = post(client, f"/loans/{loan_id}/checkout")
    assert checked_out.json()["status"] == "checked_out"

    item = get(client, f"/items/{item_id}").json()
    assert item["status"] == "checked_out"
    assert item["allowed_actions"] == ["return", "join_waitlist"]
    assert item["current_loan"]["id"] == loan_id

    returned = post(client, f"/loans/{loan_id}/return", T0 + timedelta(days=9))
    assert returned.status_code == 200
    assert returned.json()["fee_charged_paise"] == 2_000
    assert get(client, f"/members/{member_id}").json()["fee_balance_paise"] == 2_000


def test_two_checkouts_within_seconds(client: TestClient) -> None:
    loan_id = reserve(client, create_member(client), create_item(client)).json()["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post(client, f"/loans/{loan_id}/checkout"), range(2)))

    assert sorted(r.status_code for r in responses) == [200, 409]


def test_returning_twice(client: TestClient) -> None:
    loan_id = checked_out_loan(client, create_member(client), create_item(client))
    first = post(client, f"/loans/{loan_id}/return", T0 + timedelta(days=1))
    second = post(client, f"/loans/{loan_id}/return", T0 + timedelta(days=1))
    assert first.status_code == 200
    assert second.status_code == 409
    assert error_code(second) == "INVALID_TRANSITION"
    assert second.json()["error"]["type"] == "invalid_transition"


def test_return_of_a_reserved_item_is_rejected(client: TestClient) -> None:
    loan_id = reserve(client, create_member(client), create_item(client)).json()["id"]
    response = post(client, f"/loans/{loan_id}/return")
    assert response.status_code == 409


def test_checkout_at_47h59m_and_48h01m(client: TestClient) -> None:
    member_id = create_member(client)
    early = reserve(client, member_id, create_item(client, "Drill A")).json()["id"]
    late = reserve(client, member_id, create_item(client, "Drill B")).json()["id"]

    ok = post(client, f"/loans/{early}/checkout", T0 + timedelta(hours=47, minutes=59))
    expired = post(client, f"/loans/{late}/checkout", T0 + timedelta(hours=48, minutes=1))

    assert ok.status_code == 200
    assert expired.status_code == 409
    assert error_code(expired) == "RESERVATION_EXPIRED"


def test_fee_capped_at_replacement_value(client: TestClient) -> None:
    item_id = create_item(client, "Stud finder", value=15_000)
    loan_id = checked_out_loan(client, create_member(client), item_id)
    response = post(client, f"/loans/{loan_id}/return", T0 + timedelta(days=7 + 25))
    assert response.json()["fee_charged_paise"] == 15_000


def test_member_exactly_at_100_rupees_can_still_reserve(client: TestClient) -> None:
    member_id = create_member(client)
    loan_id = checked_out_loan(client, member_id, create_item(client, "Ladder"))
    later = T0 + timedelta(days=17)  # 10 days late -> ₹100
    post(client, f"/loans/{loan_id}/return", later)

    member = get(client, f"/members/{member_id}", later).json()
    assert member["fee_balance_paise"] == 10_000
    assert member["eligibility"] == {"can_borrow": True, "blocks": []}
    assert reserve(client, member_id, create_item(client, "Tiller"), later).status_code == 201


def test_member_over_100_rupees_is_blocked_with_reason(client: TestClient) -> None:
    member_id = create_member(client)
    loan_id = checked_out_loan(client, member_id, create_item(client, "Ladder"))
    later = T0 + timedelta(days=18)  # 11 days late -> ₹110
    post(client, f"/loans/{loan_id}/return", later)

    response = reserve(client, member_id, create_item(client, "Tiller"), later)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["type"] == "rule_violation"
    assert error["code"] == "FEE_BALANCE_OVER_LIMIT"
    assert error["details"]["blocks"][0]["code"] == "FEE_BALANCE_OVER_LIMIT"


def test_paying_more_than_the_balance(client: TestClient) -> None:
    member_id = create_member(client)
    loan_id = checked_out_loan(client, member_id, create_item(client))
    later = T0 + timedelta(days=10)
    post(client, f"/loans/{loan_id}/return", later)  # ₹30

    too_much = post(client, f"/members/{member_id}/payments", later, json={"amount_paise": 3_100})
    assert too_much.status_code == 422
    assert error_code(too_much) == "PAYMENT_EXCEEDS_BALANCE"

    exact = post(client, f"/members/{member_id}/payments", later, json={"amount_paise": 3_000})
    assert exact.status_code == 201
    assert exact.json()["fee_balance_paise"] == 0


def test_fourth_active_loan_is_refused(client: TestClient) -> None:
    member_id = create_member(client)
    for n in range(3):
        assert reserve(client, member_id, create_item(client, f"Tool {n}")).status_code == 201
    response = reserve(client, member_id, create_item(client, "Tool 4"))
    assert response.status_code == 422
    assert error_code(response) == "ACTIVE_LOAN_LIMIT_REACHED"


def test_cancel_reservation(client: TestClient) -> None:
    item_id = create_item(client)
    loan_id = reserve(client, create_member(client), item_id).json()["id"]
    assert post(client, f"/loans/{loan_id}/cancel").json()["status"] == "cancelled"
    assert get(client, f"/items/{item_id}").json()["status"] == "available"


def test_overdue_dashboard(client: TestClient) -> None:
    member_id = create_member(client)
    checked_out_loan(client, member_id, create_item(client, "Ladder"))
    later = T0 + timedelta(days=10)

    overdue = get(client, "/loans/overdue", later).json()
    assert overdue["total"] == 1
    loan = overdue["items"][0]
    assert loan["status"] == "overdue"
    assert loan["days_overdue"] == 3
    assert loan["accrued_fee_paise"] == 3_000
    assert loan["member_phone"] == "+919800011111"

    assert get(client, "/loans/overdue", T0).json()["total"] == 0


def test_loan_history_filters(client: TestClient) -> None:
    member_id, item_id = create_member(client), create_item(client)
    reserve(client, member_id, item_id)
    assert get(client, "/loans", member_id=member_id).json()["total"] == 1
    assert get(client, "/loans", item_id=item_id + 1).json()["total"] == 0


def test_unknown_loan_is_404(client: TestClient) -> None:
    response = post(client, "/loans/9999/checkout")
    assert response.status_code == 404
    assert error_code(response) == "NOT_FOUND"
    assert get(client, "/loans/9999").status_code == 404


def test_reserve_unknown_member_or_item_is_404(client: TestClient) -> None:
    item_id = create_item(client)
    assert reserve(client, 9999, item_id).status_code == 404
    assert reserve(client, create_member(client), 9999).status_code == 404


def test_return_with_maintenance_flag(client: TestClient) -> None:
    item_id = create_item(client)
    loan_id = checked_out_loan(client, create_member(client), item_id)
    response = post(
        client,
        f"/loans/{loan_id}/return",
        json={"send_to_maintenance": True, "condition_note": "Cracked casing"},
    )
    assert response.status_code == 200
    item = get(client, f"/items/{item_id}").json()
    assert item["status"] == "maintenance"
    assert item["allowed_actions"] == ["return_to_service", "join_waitlist"]

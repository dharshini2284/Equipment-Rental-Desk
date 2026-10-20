from datetime import timedelta

from fastapi.testclient import TestClient

from tests.api.helpers import API, create_item, create_member, error_code, get, post
from tests.conftest import T0, clock_header


class TestMembers:
    def test_create_normalises_phone_and_defaults_join_date(self, client: TestClient) -> None:
        response = post(client, "/members", json={"name": "  Ravi  ", "phone": "+91 98000-22222"})
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Ravi"
        assert body["phone"] == "+919800022222"
        assert body["joined_on"] == "2026-10-20"
        assert body["status"] == "active"
        assert body["fee_balance_paise"] == 0

    def test_duplicate_phone_is_409(self, client: TestClient) -> None:
        create_member(client, phone="+919800033333")
        response = post(client, "/members", json={"name": "B", "phone": "+919800033333"})
        assert response.status_code == 409
        assert error_code(response) == "PHONE_IN_USE"

    def test_list_search_and_filter(self, client: TestClient) -> None:
        asha = create_member(client, "Asha", "+919800044441")
        create_member(client, "Bala", "+919800044442")
        post(client, f"/members/{asha}/suspend", json={"reason": "Damage"})

        assert get(client, "/members", q="ash").json()["total"] == 1
        assert get(client, "/members", q="44442").json()["total"] == 1
        suspended = get(client, "/members", status="suspended").json()
        assert [m["id"] for m in suspended["items"]] == [asha]

    def test_patch_updates_and_rejects_status_field(self, client: TestClient) -> None:
        member_id = create_member(client)
        ok = client.patch(f"{API}/members/{member_id}", json={"name": "New Name"})
        assert ok.status_code == 200 and ok.json()["name"] == "New Name"

        sneaky = client.patch(f"{API}/members/{member_id}", json={"status": "active"})
        assert sneaky.status_code == 400

    def test_patch_phone_and_join_date(self, client: TestClient) -> None:
        member_id = create_member(client, phone="+919800066661")
        other_id = create_member(client, "Other", phone="+919800066662")
        headers = clock_header(T0)

        same_phone = client.patch(
            f"{API}/members/{member_id}", json={"phone": "+919800066661"}, headers=headers
        )
        assert same_phone.status_code == 200  # keeping your own number is not a clash
        taken = client.patch(
            f"{API}/members/{other_id}", json={"phone": "+919800066661"}, headers=headers
        )
        assert taken.status_code == 409
        future = client.patch(
            f"{API}/members/{member_id}", json={"joined_on": "2026-10-21"}, headers=headers
        )
        assert error_code(future) == "JOIN_DATE_IN_FUTURE"
        past = client.patch(
            f"{API}/members/{member_id}", json={"joined_on": "2024-01-15"}, headers=headers
        )
        assert past.json()["joined_on"] == "2024-01-15"

    def test_patch_rejects_empty_and_null(self, client: TestClient) -> None:
        member_id = create_member(client)
        assert client.patch(f"{API}/members/{member_id}", json={}).status_code == 400
        assert client.patch(f"{API}/members/{member_id}", json={"name": None}).status_code == 400

    def test_future_join_date_is_rejected(self, client: TestClient) -> None:
        response = post(
            client,
            "/members",
            json={"name": "A", "phone": "+919800055555", "joined_on": "2026-12-01"},
        )
        assert response.status_code == 422
        assert error_code(response) == "JOIN_DATE_IN_FUTURE"

    def test_suspend_and_reinstate_keep_history(self, client: TestClient) -> None:
        member_id = create_member(client)
        suspended = post(client, f"/members/{member_id}/suspend", json={"reason": "Damage"}).json()
        assert suspended["status"] == "suspended"
        assert suspended["eligibility"]["blocks"][0]["code"] == "MEMBER_SUSPENDED"

        again = post(client, f"/members/{member_id}/suspend", json={"reason": "Again"})
        assert again.status_code == 409

        later = T0 + timedelta(days=2)
        reinstated = post(client, f"/members/{member_id}/reinstate", later, json={"reason": "OK"})
        history = reinstated.json()["status_history"]
        assert [(h["from_status"], h["to_status"]) for h in history] == [
            ("active", "suspended"),
            ("suspended", "active"),
        ]

    def test_suspend_requires_reason(self, client: TestClient) -> None:
        member_id = create_member(client)
        assert (
            post(client, f"/members/{member_id}/suspend", json={"reason": "  "}).status_code == 400
        )

    def test_statement(self, client: TestClient) -> None:
        member_id = create_member(client)
        loan_id = post(
            client, "/loans", json={"member_id": member_id, "item_id": create_item(client)}
        ).json()["id"]
        post(client, f"/loans/{loan_id}/checkout")
        later = T0 + timedelta(days=12)
        post(client, f"/loans/{loan_id}/return", later)
        post(
            client,
            f"/members/{member_id}/payments",
            later,
            json={"amount_paise": 2_000, "note": "UPI"},
        )

        statement = get(client, f"/members/{member_id}/statement", later).json()
        assert statement["total_fees_charged_paise"] == 5_000
        assert statement["total_paid_paise"] == 2_000
        assert statement["fee_balance_paise"] == 3_000
        assert statement["payments"][0]["note"] == "UPI"
        assert statement["loans"][0]["fee_charged_paise"] == 5_000

    def test_delete(self, client: TestClient) -> None:
        member_id = create_member(client)
        assert client.delete(f"{API}/members/{member_id}").status_code == 204
        assert get(client, f"/members/{member_id}").status_code == 404

    def test_delete_with_history_is_409(self, client: TestClient) -> None:
        member_id = create_member(client)
        post(client, "/loans", json={"member_id": member_id, "item_id": create_item(client)})
        response = client.delete(f"{API}/members/{member_id}")
        assert response.status_code == 409
        assert error_code(response) == "MEMBER_HAS_HISTORY"


class TestItems:
    def test_create_and_get(self, client: TestClient) -> None:
        item_id = create_item(client)
        item = get(client, f"/items/{item_id}").json()
        assert item["status"] == "available"
        assert item["allowed_actions"] == ["reserve", "send_to_maintenance"]
        assert item["current_loan"] is None

    def test_list_filters_and_paginates(self, client: TestClient) -> None:
        for n in range(3):
            create_item(client, f"Drill {n}")
        create_item(client, "Ladder")
        page = get(client, "/items", q="drill", limit=2, offset=0).json()
        assert page["total"] == 3 and len(page["items"]) == 2
        assert get(client, "/items", status="overdue").json()["total"] == 0
        assert get(client, "/items", category="POWER TOOLS").json()["total"] == 4
        assert get(client, "/items/categories").json() == ["Power tools"]

    def test_maintenance_endpoints(self, client: TestClient) -> None:
        item_id = create_item(client)
        sent = post(client, f"/items/{item_id}/send-to-maintenance", json={"condition_note": "Oil"})
        assert sent.json()["status"] == "maintenance"
        assert post(client, f"/items/{item_id}/send-to-maintenance").status_code == 409
        back = post(client, f"/items/{item_id}/return-to-service")
        assert back.json()["status"] == "available"
        assert back.json()["condition_note"] == "Oil"

    def test_invalid_transition_explains_allowed_actions(self, client: TestClient) -> None:
        item_id = create_item(client)
        response = post(client, f"/items/{item_id}/return-to-service")
        assert response.status_code == 409
        details = response.json()["error"]["details"]
        assert details["current_status"] == "available"
        assert details["allowed_actions"] == ["reserve", "send_to_maintenance"]

    def test_patch_item(self, client: TestClient) -> None:
        item_id = create_item(client)
        response = client.patch(
            f"{API}/items/{item_id}",
            json={"replacement_value_paise": 99_900},
            headers=clock_header(T0),
        )
        assert response.status_code == 200
        assert response.json()["replacement_value_paise"] == 99_900

    def test_cannot_patch_status(self, client: TestClient) -> None:
        item_id = create_item(client)
        response = client.patch(f"{API}/items/{item_id}", json={"status": "available"})
        assert response.status_code == 400

    def test_delete_item(self, client: TestClient) -> None:
        item_id = create_item(client)
        assert client.delete(f"{API}/items/{item_id}").status_code == 204
        assert client.delete(f"{API}/items/{item_id}").status_code == 404

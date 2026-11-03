"""Price negotiation on the plan screen: up to max_discount_pct in two steps, never below the catalogue minimum,
then a salesperson's call (phone + consent). Offers come from pricing_settings.json, never from the AI."""
import json

import pytest

from backend.app import main, negotiate
from backend.app.negotiate import clean_phone, next_offer, rupees
from tests.test_api import ANSWERS, client  # noqa: F401  (pytest fixture)


def test_two_steps_then_a_salesperson():
    assert next_offer(1, room=13.0, current=0) == 5
    assert next_offer(2, room=13.0, current=5) == 10
    assert next_offer(3, room=13.0, current=10) is None


def test_offers_stop_at_the_catalogue_floor():
    assert next_offer(1, room=3.0, current=0) == 3          # less room than the first step
    assert next_offer(2, room=3.0, current=3) is None       # nothing more to give: salesperson
    assert next_offer(1, room=0.0, current=0) is None       # already at the floor (e.g. 24-month contract)


def test_settings_file_is_checked(tmp_path, monkeypatch):
    bad = tmp_path / "pricing_settings.json"
    bad.write_text(json.dumps({"first_offer_pct": 20, "max_discount_pct": 10, "sales_callback_hours": 24}))
    monkeypatch.setattr(negotiate, "SETTINGS_FILE", bad)
    negotiate.settings.cache_clear()
    with pytest.raises(ValueError):
        negotiate.settings()
    negotiate.settings.cache_clear()


@pytest.mark.parametrize("raw,ok", [("+91 98765-43210", "9876543210"), ("09876543210", "9876543210"),
                                    ("९८७६५४३२१०", "9876543210"), ("12345", None), ("5876543210", None)])
def test_phone_numbers(raw, ok):
    assert clean_phone(raw) == ok


def test_indian_digit_grouping():
    assert [rupees(n) for n in (999, 6968, 123456)] == ["999", "6,968", "1,23,456"]


def _clinic(client, extra=None):
    answers = {**ANSWERS, "segment": "prof", "need:phone_system": "no", "need:backup": "no", "need:failover": "yes"}
    r = client.post("/api/applications", json={"language": "en"}).json()
    app_id, out = r["id"], r
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": answers[out["question"]["slot"]]}).json()
    for body in extra or []:
        client.post(f"/api/applications/{app_id}/plan", json=body)
    return app_id


def test_negotiation_journey_and_sales_callback(client, monkeypatch):
    monkeypatch.setenv("BACKOFFICE_KEY", "k")
    app_id = _clinic(client)
    start = client.post(f"/api/applications/{app_id}/plan", json={}).json()["quote"]
    seen = [client.post(f"/api/applications/{app_id}/price-request").json() for _ in range(3)]
    assert [s["status"] for s in seen] == ["offer", "final", "handoff"]
    q1, q2 = seen[0]["quote"], seen[1]["quote"]
    assert start["monthly_with_gst"] > q1["monthly_with_gst"] > q2["monthly_with_gst"]
    assert q1["discount_pct"] == 5 and q2["discount_pct"] == 10
    assert q2["monthly_total"] >= q2["floor_total"]
    assert "10%" in seen[1]["message"] and "24 hours" in seen[2]["message"]
    assert seen[2]["quote"]["discount_pct"] == 10                        # asking again keeps the best offer

    url = f"/api/applications/{app_id}/sales-callback"
    assert client.post(url, json={"phone": "9876543210", "consent": False}).status_code == 422
    assert client.post(url, json={"phone": "12345", "consent": True}).status_code == 422
    ok = client.post(url, json={"phone": "+91 98765 43210", "consent": True, "target_monthly": 5500}).json()
    assert ok["ok"] and ok["reference"] in ok["message"]

    status = client.get(f"/api/applications/{app_id}").json()
    assert "9876543210" not in json.dumps(status)                         # masked for the owner's screens and logs
    office = client.get("/api/backoffice/applications", headers={"x-admin-key": "k"}).json()
    lead = office[0]                                                      # calls to make come first
    assert lead["sales_callback"]["phone"] == "9876543210" and lead["sales_callback"]["target_monthly"] == 5500
    assert lead["price"]["discount_pct"] == 10

    accepted = client.post(f"/api/applications/{app_id}/accept").json()   # owner can still take the offer
    assert next(s for s in accepted["timeline"] if s["step"] == "quote_accepted")["discount_pct"] == 10
    assert client.post(f"/api/applications/{app_id}/price-request").status_code == 409
    client.delete(f"/api/applications/{app_id}")


def test_plan_already_at_the_floor_goes_straight_to_a_salesperson(client):
    app_id = _clinic(client, extra=[{"contract_months": 24}])           # 24 months = catalogue minimum
    out = client.post(f"/api/applications/{app_id}/price-request").json()
    assert out["status"] == "handoff" and "lowest price" in out["message"]
    assert out["quote"]["discount"] == 0


def test_discount_survives_plan_changes_but_never_breaks_the_floor(client):
    app_id = _clinic(client)
    for _ in range(2):
        client.post(f"/api/applications/{app_id}/price-request")
    full = client.post(f"/api/applications/{app_id}/plan", json={"tier": "full"}).json()["quote"]
    assert full["discount_pct"] == 10
    two_years = client.post(f"/api/applications/{app_id}/plan", json={"contract_months": 24}).json()["quote"]
    assert two_years["monthly_total"] == two_years["floor_total"] and two_years["discount"] == 0

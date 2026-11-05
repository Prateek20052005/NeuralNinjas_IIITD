"""Price negotiation in the chat after the plan: the first request gets no discount (cheaper plan and longer contract
shown instead); if the owner insists, 5% then 10%, never below the catalogue minimum; then a salesperson's call
(phone + consent). Offers come from pricing_settings.json, never from the AI."""
import json

import pytest

from backend.app import main, negotiate
from backend.app.negotiate import clean_phone, negotiation_step, next_offer, rupees, wants_lower_price
from tests.test_advisor import FakeLLM
from tests.test_api import ANSWERS, client, verify_phone  # noqa: F401  (pytest fixture)


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


def say(client, app_id, text):
    return client.post(f"/api/applications/{app_id}/message", json={"text": text})


def test_no_discount_first_then_five_then_ten_then_a_salesperson():
    assert [negotiation_step(n, room=13.0, current=c) for n, c in [(1, 0), (2, 0), (3, 5), (4, 10)]] == \
        [("pushback", None), ("offer", 5.0), ("final", 10.0), ("handoff", None)]
    assert negotiation_step(2, room=0.0, current=0) == ("handoff", None)     # already at the catalogue floor


@pytest.mark.parametrize("text,asks", [("can you give me a discount?", True), ("this is too expensive", True),
                                       ("thoda kam karo bhai", True), ("कुछ छूट मिलेगी?", True),
                                       ("விலை குறைக்க முடியுமா", True), ("ಬೆಲೆ ಕಡಿಮೆ ಮಾಡಿ", True),
                                       ("ధర తగ్గించండి", True), ("ભાવ ઓછો કરો", True),
                                       ("what is static IP?", False), ("looks good", False), ("I need 2 lines", False),
                                       # words that are about price only when money is mentioned
                                       ("Will the firewall reduce virus attacks?", False),
                                       ("Is it too much effort to set up CCTV?", False), ("camera kam karo", False),
                                       ("can you reduce the price?", True), ("too much, reduce it to 5,000", True),
                                       ("kam karo rate", True), ("कम करो कीमत", True), ("it's expensive for my budget", True)])
def test_price_requests_in_seven_languages(text, asks):
    assert wants_lower_price(text) is asks


def test_negotiation_in_the_chat_and_sales_callback(client, monkeypatch):
    monkeypatch.setenv("BACKOFFICE_KEY", "k")
    app_id = _clinic(client)
    start = client.post(f"/api/applications/{app_id}/plan", json={}).json()["quote"]
    seen = [say(client, app_id, "can you give me a discount?").json() for _ in range(4)]
    assert [s["negotiation"]["status"] for s in seen] == ["pushback", "offer", "final", "handoff"]
    first = seen[0]
    assert first["quote"]["discount"] == 0                                   # first request: no discount...
    assert any("Basic plan" in m for m in first["messages"])                 # ...but the honest ways to pay less
    assert any("24-month contract" in m for m in first["messages"])
    q1, q2 = seen[1]["quote"], seen[2]["quote"]
    assert start["monthly_with_gst"] > q1["monthly_with_gst"] > q2["monthly_with_gst"]
    assert q1["discount_pct"] == 5 and q2["discount_pct"] == 10
    assert q2["monthly_total"] >= q2["floor_total"]
    assert "10%" in seen[2]["messages"][0] and "24 hours" in seen[3]["messages"][0]
    assert seen[3]["quote"]["discount_pct"] == 10                            # asking again keeps the best offer
    assert client.post(f"/api/applications/{app_id}/plan", json={}).json()["quote"]["discount_pct"] == 10

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

    verify_phone(client, app_id)   # accepting needs a verified mobile number
    accepted = client.post(f"/api/applications/{app_id}/accept").json()   # owner can still take the offer
    assert next(s for s in accepted["timeline"] if s["step"] == "quote_accepted")["discount_pct"] == 10
    assert say(client, app_id, "any discount?").status_code == 409         # no price talk after accepting
    client.delete(f"/api/applications/{app_id}")


def test_other_messages_after_the_plan_get_no_discount(client):
    app_id = _clinic(client)
    out = say(client, app_id, "looks good, thanks").json()
    assert "negotiation" not in out and "Your plan" in out["messages"][0]
    assert client.post(f"/api/applications/{app_id}/plan", json={}).json()["quote"]["discount"] == 0


def test_plan_already_at_the_floor_goes_to_a_salesperson_without_a_discount(client):
    app_id = _clinic(client, extra=[{"contract_months": 24}])           # 24 months = catalogue minimum
    first = say(client, app_id, "too expensive").json()
    assert first["negotiation"]["status"] == "pushback"
    out = say(client, app_id, "please reduce the price").json()
    assert out["negotiation"]["status"] == "handoff" and "lowest price" in out["messages"][0]
    assert out["quote"]["discount"] == 0


def test_discount_survives_plan_changes_but_never_breaks_the_floor(client):
    app_id = _clinic(client)
    for _ in range(3):
        say(client, app_id, "discount please")
    full = client.post(f"/api/applications/{app_id}/plan", json={"tier": "full"}).json()["quote"]
    assert full["discount_pct"] == 10
    two_years = client.post(f"/api/applications/{app_id}/plan", json={"contract_months": 24}).json()["quote"]
    assert two_years["monthly_total"] == two_years["floor_total"] and two_years["discount"] == 0


def test_ai_spots_a_price_request_but_never_sets_the_amount(client, monkeypatch):
    app_id = _clinic(client)
    monkeypatch.setattr(main.advisor, "llm", FakeLLM(
        {"wants_lower_price": True, "say": "I can give you 50% off today!"},       # the AI overreaching
        {"wants_lower_price": False, "say": "Static IP gives you a fixed address for CCTV. It costs ₹250 a month."}))
    out = say(client, app_id, "can you do something for me on this?").json()   # no price keyword: the AI decides
    assert out["negotiation"]["status"] == "pushback" and out["quote"]["discount"] == 0
    assert not any("50%" in m for m in out["messages"])                         # the AI's own words are not used
    answer = say(client, app_id, "what does static IP do").json()
    assert answer["messages"] == ["Static IP gives you a fixed address for CCTV."]   # the price sentence is dropped

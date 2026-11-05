"""The whole owner journey through the HTTP API, in scripted mode (no AI calls), with real OCR on the photos."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import main

DOCS = Path(__file__).resolve().parent.parent / "data" / "kyc_documents"
ANSWERS = {"gstin": "27XUIXG0767D1ZP", "gst_confirm": "yes", "segment": "mfg", "employees": "12", "sites": "1",
           "current": "home", "internet": "fibre", "existing": "no", "need:machines": "4", "need:vehicles": "0", "need:firewall": "yes"}


class NoLLM:
    available = False
    tokens_used = 0


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main.advisor, "llm", NoLLM())
    return TestClient(main.app)


def upload(client, app_id, doc_type, applicant="K03"):
    with open(DOCS / f"{applicant}_{doc_type}.png", "rb") as f:
        return client.post(f"/api/applications/{app_id}/documents/{doc_type}", files={"file": ("p.png", f, "image/png")})


def verify_phone(client, app_id, phone="9876543210"):
    """Demo mode: the one-time code comes back in the response (no SMS in the prototype)."""
    code = client.post(f"/api/applications/{app_id}/phone", json={"phone": phone}).json()["demo_code"]
    assert client.post(f"/api/applications/{app_id}/phone/verify", json={"code": code}).status_code == 200


def chat_to_quote(client):
    r = client.post("/api/applications", json={"language": "en"}).json()
    app_id, out = r["id"], r
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": ANSWERS[out["question"]["slot"]]}).json()
    return app_id, out["recommendation"]


def test_full_journey_from_chat_to_installation(client):
    app_id, rec = chat_to_quote(client)
    assert rec["quote"]["valid"] and any(x["id"] == "P24" for x in rec["core"])   # 4 machines -> IoT sensors

    if rec["addons"]:                                                             # switch an extra on, see the price move
        before = rec["quote"]["monthly_with_gst"]
        r = client.post(f"/api/applications/{app_id}/addons", json={"product_id": rec["addons"][0]["id"], "on": True})
        assert r.status_code == 200 and r.json()["quote"]["monthly_with_gst"] > before
    assert client.post(f"/api/applications/{app_id}/addons", json={"product_id": "P13", "on": True}).status_code == 422
    verify_phone(client, app_id)   # accepting needs a verified mobile number
    assert client.post(f"/api/applications/{app_id}/accept").json()["accepted"]

    assert upload(client, app_id, "gst_certificate").status_code == 403          # no consent yet
    r = client.post(f"/api/applications/{app_id}/consent", json={"purposes": ["kyc"]})
    assert r.json()["consent"]["version"]
    for t in ("gst_certificate", "udyam_certificate", "address_proof", "signatory_id"):
        r = upload(client, app_id, t).json()
        assert r["ok"], r
    assert r["fields"]["id_no"].count("*") >= 4                                    # ID numbers come back masked

    res = client.post(f"/api/applications/{app_id}/kyc").json()
    assert res["decision"] == "PASS" and "evidence" not in res                     # owner never sees back-office notes
    steps = [s["step"] for s in client.get(f"/api/applications/{app_id}").json()["timeline"]]
    assert steps[-1] == "installation_booked" and "consent_given" in steps

    assert client.delete(f"/api/applications/{app_id}").json()["deleted"]
    assert client.get(f"/api/applications/{app_id}").status_code == 404


def test_blurred_or_wrong_photo_is_flagged_at_upload(client):
    app_id, _ = chat_to_quote(client)
    client.post(f"/api/applications/{app_id}/consent", json={"purposes": ["kyc", "contact"]})
    r = upload(client, app_id, "gst_certificate", "K04").json()
    assert not r["ok"] and "couldn't read" in r["message"]
    with open(DOCS / "K03_signatory_id.png", "rb") as f:
        r = client.post(f"/api/applications/{app_id}/documents/address_proof",
                        files={"file": ("p.png", f, "image/png")}).json()
    assert not r["ok"] and "doesn't look like" in r["message"]
    r = client.post(f"/api/applications/{app_id}/documents/address_proof", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_consent_must_include_kyc_and_back_office_needs_a_key(client, monkeypatch):
    app_id, _ = chat_to_quote(client)
    assert client.post(f"/api/applications/{app_id}/consent", json={"purposes": ["contact"]}).status_code == 422
    monkeypatch.delenv("BACKOFFICE_KEY", raising=False)
    assert client.get("/api/backoffice/applications").status_code == 401
    monkeypatch.setenv("BACKOFFICE_KEY", "test-key")
    rows = client.get("/api/backoffice/applications", headers={"x-admin-key": "test-key"}).json()
    assert rows and all("*" in r["gstin"] or not r["gstin"] for r in rows)


def test_hindi_strings_and_consent_text(client):
    c = client.get("/api/consent/hi").json()
    assert "KYC" in c["body"] and c["purposes"][0]["required"]
    assert client.get("/api/i18n/mr").json()["doc.gst_certificate"] == "GST प्रमाणपत्र"


def test_last_internet_line_cannot_be_switched_off_and_notes_are_translated(client):
    r = client.post("/api/applications", json={"language": "hi"}).json()
    app_id, out = r["id"], r
    answers = {**ANSWERS, "segment": "prof", "need:phone_system": "yes", "need:backup": "no", "need:failover": "yes"}
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": answers[out["question"]["slot"]]}).json()
    core = {x["id"] for x in out["recommendation"]["core"]}
    line = next(iter(core & {"P01", "P02", "P03", "P04", "P05", "P06"}))
    r = client.post(f"/api/applications/{app_id}/addons", json={"product_id": line, "on": False})
    assert r.status_code == 422 and "इंटरनेट" in r.json()["detail"]
    if "P09" in core:   # backup router needs an internet line: switching it off alone is fine
        r = client.post(f"/api/applications/{app_id}/addons", json={"product_id": "P09", "on": False})
        assert r.status_code == 200 and "P09" not in r.json()["items"]


def test_owner_without_gst_uploads_only_address_proof_and_id(client):
    answers = {**ANSWERS, "gstin": "none", "segment": "micro", "city": "Pune", "employees": "3",
               "need:billing_pos": "no", "need:whatsapp": "no", "need:cctv": "no"}
    r = client.post("/api/applications", json={"language": "en"}).json()
    app_id, out = r["id"], r
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": answers[out["question"]["slot"]]}).json()
    verify_phone(client, app_id)   # accepting needs a verified mobile number
    client.post(f"/api/applications/{app_id}/accept")
    client.post(f"/api/applications/{app_id}/consent", json={"purposes": ["kyc"]})
    docs = client.get(f"/api/applications/{app_id}").json()["documents"]
    assert {k for k, v in docs.items() if v["required"]} == {"address_proof", "signatory_id"}
    for doc_type in ("address_proof", "signatory_id"):
        assert upload(client, app_id, doc_type).json()["ok"]
    assert client.post(f"/api/applications/{app_id}/kyc").json()["decision"] == "PASS"


def test_mobile_only_plan_can_still_switch_extras(client):
    answers = {**ANSWERS, "gstin": "none", "segment": "micro", "city": "Pune", "employees": "3",
               "current": "mobile", "internet": "mobile", "need:billing_pos": "no", "need:whatsapp": "no"}
    r = client.post("/api/applications", json={"language": "en"}).json()
    app_id, out = r["id"], r
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": answers[out["question"]["slot"]]}).json()
    rec = out["recommendation"]
    assert [x["id"] for x in rec["core"]] == ["P07"] and rec["addons"]
    r = client.post(f"/api/applications/{app_id}/addons", json={"product_id": rec["addons"][0]["id"], "on": True})
    assert r.status_code == 200 and r.json()["quote"]["valid"]


def test_plan_tiers_contract_and_setup_choices(client):
    answers = {**ANSWERS, "segment": "prof", "need:phone_system": "no", "need:backup": "no", "need:failover": "yes"}
    r = client.post("/api/applications", json={"language": "en"}).json()
    app_id, out = r["id"], r
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": answers[out["question"]["slot"]]}).json()
    plan = client.post(f"/api/applications/{app_id}/plan", json={}).json()
    prices = {t["id"]: t["monthly_with_gst"] for t in plan["tiers"]}
    assert plan["tier"] == "recommended" and prices["basic"] < prices["recommended"] < prices["full"]

    basic = client.post(f"/api/applications/{app_id}/plan", json={"tier": "basic"}).json()
    assert basic["quote"]["monthly_with_gst"] == prices["basic"]
    longer = client.post(f"/api/applications/{app_id}/plan", json={"contract_months": 24}).json()
    assert longer["quote"]["contract_months"] == 24
    assert longer["quote"]["monthly_with_gst"] < basic["quote"]["monthly_with_gst"]
    assert all(longer["unit_prices"][pid] == main.load_catalogue()[pid].price_min for pid in longer["unit_prices"])
    spread = client.post(f"/api/applications/{app_id}/plan", json={"setup_months": 12}).json()["quote"]
    # a new customer with a small order: setup is free, so there is nothing to spread (spreading: test_rules.py)
    assert spread["welcome"] and spread["setup_due"] == 0 and spread["setup_months"] == 1

    verify_phone(client, app_id)   # accepting needs a verified mobile number
    accepted = client.post(f"/api/applications/{app_id}/accept").json()
    assert accepted["quote"]["contract_months"] == 24 and accepted["quote"]["setup_due"] == 0
    step = next(s for s in accepted["timeline"] if s["step"] == "quote_accepted")
    assert step["tier"] == "basic" and step["contract_months"] == 24
    assert client.post(f"/api/applications/{app_id}/plan", json={"tier": "full"}).status_code == 409
    assert client.post(f"/api/applications/{app_id}/plan", json={"tier": "gold"}).status_code == 409


# ---------- review fixes (Nov 2026) ----------

def test_cancelled_gstin_still_needs_the_certificate_and_is_rejected(client):
    # K01 types a cancelled GSTIN: the GST certificate stays required and the registry check rejects it
    app_id = client.post("/api/applications", json={"language": "en"}).json()["id"]
    client.post(f"/api/applications/{app_id}/message", json={"text": "37IHKXV5167L1ZS"})
    docs = client.get(f"/api/applications/{app_id}").json()["documents"]
    assert docs["gst_certificate"]["required"] and docs["udyam_certificate"]["required"]
    client.post(f"/api/applications/{app_id}/consent", json={"purposes": ["kyc"]})
    for doc_type in ("gst_certificate", "address_proof", "signatory_id"):
        assert upload(client, app_id, doc_type, "K01").status_code == 200
    assert client.post(f"/api/applications/{app_id}/kyc").json()["decision"] == "REJECT"
    assert "gstin_cancelled" in main.store.get(app_id).kyc.codes


def test_only_offered_contract_lengths_and_setup_spreads(client):
    app_id, rec = chat_to_quote(client)
    plan = f"/api/applications/{app_id}/plan"
    offered = [c["months"] for c in rec["quote"]["contract_options"]]
    for bad in (1000, 36, -5, 0, 7):
        assert bad in offered or client.post(plan, json={"contract_months": bad}).status_code == 422
    assert client.post(plan, json={"contract_months": offered[-1]}).json()["quote"]["contract_months"] == offered[-1]
    assert client.post(plan, json={"setup_months": 7}).status_code == 422
    assert client.post(plan, json={"setup_months": 6}).status_code == 200


def test_accept_twice_and_callback_rules(client):
    app_id, _ = chat_to_quote(client)
    cb = f"/api/applications/{app_id}/sales-callback"
    assert client.post(cb, json={"phone": "98765 43210", "consent": True}).status_code == 200
    a = main.store.get(app_id)
    assert a.callback["requested_at"] == main.TODAY.isoformat()          # same calendar as the rest of the app
    verify_phone(client, app_id)   # accepting needs a verified mobile number
    assert client.post(f"/api/applications/{app_id}/accept").status_code == 200
    assert client.post(f"/api/applications/{app_id}/accept").status_code == 200   # second tap: no error...
    assert sum(s["step"] == "quote_accepted" for s in a.timeline) == 1             # ...and recorded once
    assert client.post(cb, json={"phone": "98765 43210", "consent": True}).status_code == 409   # plan already accepted
    fresh = client.post("/api/applications", json={"language": "en"}).json()["id"]
    assert client.post(f"/api/applications/{fresh}/sales-callback",
                       json={"phone": "98765 43210", "consent": True}).status_code == 409   # no quote yet
    for done in (app_id, fresh):   # leave no callback behind for the back-office tests
        assert client.delete(f"/api/applications/{done}").json()["deleted"]


def test_progress_status_survives_reload_and_uses_the_case_date(client, monkeypatch):
    monkeypatch.setenv("APP_TODAY", "2026-07-15")
    r = client.post("/api/applications", json={"language": "en"}).json()
    app_id, q = r["id"], r["question"]
    assert (q["step"], q["steps"]) == (1, 10)                  # GST number first; confirm step added once it's known
    out = client.post(f"/api/applications/{app_id}/message", json={"text": ANSWERS["gstin"]}).json()
    assert out["question"]["slot"] == "gst_confirm" and out["question"]["step"] == 2
    while out.get("question"):
        assert 1 <= out["question"]["step"] <= out["question"]["steps"]
        out = client.post(f"/api/applications/{app_id}/message", json={"text": ANSWERS[out["question"]["slot"]]}).json()
    verify_phone(client, app_id)   # accepting needs a verified mobile number
    client.post(f"/api/applications/{app_id}/accept")
    client.post(f"/api/applications/{app_id}/consent", json={"purposes": ["kyc"]})
    upload(client, app_id, "gst_certificate")
    with open(DOCS / "K03_signatory_id.png", "rb") as f:     # an ID photo sent as the bill: needs a retake
        client.post(f"/api/applications/{app_id}/documents/address_proof", files={"file": ("p.png", f, "image/png")})
    s = client.get(f"/api/applications/{app_id}").json()      # what the documents screen loads after a reload
    docs = s["documents"]
    assert docs["gst_certificate"]["ok"] and docs["gst_certificate"]["fields"]
    assert docs["address_proof"]["uploaded"] and not docs["address_proof"]["ok"]
    assert "doesn't look like" in docs["address_proof"]["message"]
    assert "ok" not in docs["signatory_id"]                   # not uploaded yet
    assert all(step["at"].startswith("2026-07-15") for step in s["timeline"])   # same calendar as prices and dates
    assert s["consent"]["given_at"].startswith("2026-07-15")
    assert s["retention_hours"] > 0 and s["delete_after"] >= "2026-07-15"
    assert client.delete(f"/api/applications/{app_id}").json()["deleted"]


def test_when_basic_equals_recommended_the_selected_card_is_shown(client):
    answers = {**ANSWERS, "gstin": "none", "segment": "micro", "city": "Pune", "employees": "3",
               "need:billing_pos": "no", "need:whatsapp": "no", "need:cctv": "no"}
    r = client.post("/api/applications", json={"language": "en"}).json()
    app_id, out = r["id"], r
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": answers[out["question"]["slot"]]}).json()
    plan = client.post(f"/api/applications/{app_id}/plan", json={}).json()
    ids = [t["id"] for t in plan["tiers"]]
    assert plan["tier"] in ids and ids == sorted(ids, key=["basic", "recommended", "full"].index)


def test_sales_call_uses_the_verified_number_unless_another_is_given(client):
    app_id, _ = chat_to_quote(client)
    cb = f"/api/applications/{app_id}/sales-callback"
    assert client.post(cb, json={"consent": True}).status_code == 422             # no number at all
    verify_phone(client, app_id, phone="9876543210")
    assert client.post(cb, json={"consent": True}).status_code == 200            # not asked again
    assert main.store.get(app_id).callback["phone"] == "9876543210"
    assert client.post(cb, json={"phone": "9123456780", "consent": True}).status_code == 200
    assert main.store.get(app_id).callback["phone"] == "9123456780"               # the owner chose another one
    assert client.delete(f"/api/applications/{app_id}").json()["deleted"]

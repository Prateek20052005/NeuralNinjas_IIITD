"""People in the loop and the order after acceptance: hand-offs to the business team, channel partners and their
limited back-office view, the access log, the per-product tracker, keeping orders, spend comparison, e-sign and
DigiLocker (demo)."""
from datetime import timedelta

import pytest

from backend.app import main, store as store_module
from backend.app.store import Store
from tests.test_api import ANSWERS, chat_to_quote, client, upload, verify_phone  # noqa: F401  (pytest fixture)

STAFF, PARTNER = {"x-admin-key": "staff-key"}, {"x-admin-key": "raj-key"}


@pytest.fixture()
def office(client, monkeypatch):
    monkeypatch.setenv("BACKOFFICE_KEY", "staff-key")
    monkeypatch.setenv("PARTNER_KEYS", "RAJ01=raj-key;SHAH02=shah-key")
    monkeypatch.delenv("APP_STATE_DIR", raising=False)   # a clean in-memory store per test, not saved files
    monkeypatch.setattr(main, "store", Store())
    main._warm_predictor()
    return client


def answer_all(client, app_id, out, answers=ANSWERS):
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": answers[out["question"]["slot"]]}).json()
    return out


def booked_order(client, **start):
    """Chat -> accept -> consent -> 4 photos -> KYC PASS (installation booked)."""
    r = client.post("/api/applications", json={"language": "en", **start}).json()
    answer_all(client, r["id"], r)
    verify_phone(client, r["id"])
    client.post(f"/api/applications/{r['id']}/accept")
    client.post(f"/api/applications/{r['id']}/consent", json={"purposes": ["kyc"]})
    for t in ("gst_certificate", "udyam_certificate", "address_proof", "signatory_id"):
        upload(client, r["id"], t)
    assert client.post(f"/api/applications/{r['id']}/kyc").json()["decision"] == "PASS"
    return r["id"]


# ---------- 1. hand-off to the business team ----------

def test_a_factory_plan_offers_a_specialist_with_the_answers_attached(office):
    app_id, _ = chat_to_quote(office)                       # a 12-person factory (ANSWERS)
    plan = office.post(f"/api/applications/{app_id}/plan", json={}).json()
    assert "factory" in plan["handoff"]
    r = office.post(f"/api/applications/{app_id}/sales-callback",
                    json={"consent": True, "phone": "9876500000", "reason": "factory"}).json()
    assert r["ok"] and "business team" in r["message"]
    row = office.get("/api/backoffice/applications", headers=STAFF).json()[0]
    assert row["sales_callback"]["reason"] == "factory" and row["sales_callback"]["phone"] == "9876500000"
    assert "12 people" in row["summary"] and "machines" in row["summary"].lower()
    assert "27XUIXG0767D1ZP" not in row["summary"]          # no ID numbers in the summary


def test_unknown_callback_reason_is_refused(office):
    app_id, _ = chat_to_quote(office)
    r = office.post(f"/api/applications/{app_id}/sales-callback", json={"consent": True, "phone": "9876500000",
                                                                          "reason": "free stuff"})
    assert r.status_code == 422


def test_a_shop_needs_no_specialist(office):
    answers = {**ANSWERS, "segment": "micro", "employees": "3", "need:billing_pos": "yes", "need:whatsapp": "no",
               "need:cctv": "no"}
    r = office.post("/api/applications", json={"language": "en"}).json()
    answer_all(office, r["id"], r, answers)
    assert office.post(f"/api/applications/{r['id']}/plan", json={}).json()["handoff"] == []


def test_a_chat_that_keeps_failing_offers_a_person(office):
    r = office.post("/api/applications", json={"language": "en"}).json()
    app_id = r["id"]
    office.post(f"/api/applications/{app_id}/message", json={"text": "27XUIXG0767D1ZP"})
    office.post(f"/api/applications/{app_id}/message", json={"text": "yes"})
    outs = [office.post(f"/api/applications/{app_id}/message", json={"text": "asdf qwerty"}).json() for _ in range(3)]
    assert "handoff" not in outs[1] and outs[2]["handoff"] == "unclear"
    assert any("ask our team to call" in m for m in outs[2]["messages"])
    # a person can be asked for before there is any plan
    ok = office.post(f"/api/applications/{app_id}/sales-callback",
                     json={"consent": True, "phone": "9876500000", "reason": "unclear"})
    assert ok.status_code == 200


# ---------- 3. owners without GST ----------

def test_no_gst_explains_what_registering_adds_and_offers_help(office):
    r = office.post("/api/applications", json={"language": "hi"}).json()
    out = office.post(f"/api/applications/{r['id']}/message", json={"slot": "gstin", "value": "none"}).json()
    assert out["handoff"] == "gst_help"
    assert any("WhatsApp Business API" in m and "GST" in m for m in out["messages"])
    nxt = office.post(f"/api/applications/{r['id']}/message", json={"slot": "existing", "value": "no"}).json()
    assert "handoff" not in nxt                               # said once, not on every turn


# ---------- 2. partners, roles and the access log ----------

def test_partner_link_is_kept_and_partners_see_only_their_own_without_ids(office):
    mine = office.post("/api/applications", json={"language": "en", "ref": "raj01", "assisted": True}).json()
    assert mine["partner"]["name"] == "Raj Telecom" and mine["partner"]["assisted"]
    answer_all(office, mine["id"], mine)
    office.post(f"/api/applications/{mine['id']}/sales-callback", json={"consent": True, "phone": "9876500000",
                                                                         "reason": "factory"})
    office.post("/api/applications", json={"language": "en", "ref": "SHAH02"})       # someone else's
    office.post("/api/applications", json={"language": "en", "ref": "NOT-A-PARTNER"})  # ignored, not an error

    rows = office.get("/api/backoffice/applications", headers=PARTNER).json()
    assert [r["id"] for r in rows] == [mine["id"][:6]]
    row = rows[0]
    assert row["gstin"] is None and row["documents"] == {} and "9876500000" not in str(row)
    assert office.get("/api/backoffice/me", headers=PARTNER).json()["role"] == "partner"
    for page in ("stats", "customers", "leads", "access-log"):
        assert office.get(f"/api/backoffice/{page}", headers=PARTNER).status_code == 403

    stats = office.get("/api/backoffice/stats", headers=STAFF).json()
    raj = next(p for p in stats["partners"] if p["code"] == "RAJ01")
    assert raj["applications"] == 1 and raj["assisted"] == 1
    log = office.get("/api/backoffice/access-log", headers=STAFF).json()
    assert any(e["who"] == "partner RAJ01" and e.get("denied") and e["what"] == "statistics" for e in log)
    assert any(e["who"] == "partner RAJ01" and e["what"] == "applications" for e in log)


def test_wrong_keys_are_refused_and_logged(office):
    assert office.get("/api/backoffice/applications", headers={"x-admin-key": "guess"}).status_code == 401
    log = office.get("/api/backoffice/access-log", headers=STAFF).json()
    assert log[1]["who"] == "unknown key" and log[1]["denied"]      # [0] is this view of the log itself


def test_access_log_survives_a_restart_encrypted(tmp_path):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    s = Store(state_dir=str(tmp_path), key=key)
    s.audit("staff", "applications")
    assert b"applications" not in (tmp_path / "access-log.enc").read_bytes()
    assert Store(state_dir=str(tmp_path), key=key).audit_log()[0]["what"] == "applications"


# ---------- 4. per-product tracker, 8. e-sign ----------

def test_each_product_has_its_own_ready_by_date_and_goes_live(office):
    app_id = booked_order(office, ref="RAJ01")
    status = office.get(f"/api/applications/{app_id}").json()
    assert status["esign"]["reference"] and len(status["esign"]["fingerprint"]) == 64
    products = status["products"]
    assert products and all(p["status"] == "installing" and p["ready_by"] for p in products)
    days = {p["product_id"]: p["install_days"] for p in products}
    assert len(set(p["ready_by"] for p in products)) == len(set(days.values()))   # different install times

    ref = app_id[:6].upper()
    first = products[0]["product_id"]
    assert office.post(f"/api/backoffice/applications/{ref}/installed", json={"product_id": first},
                       headers={"x-admin-key": "shah-key"}).status_code == 404   # not this partner's order
    for p in products:   # the referring partner (their technician) may mark installs
        office.post(f"/api/backoffice/applications/{ref}/installed", json={"product_id": p["product_id"]},
                    headers=PARTNER)
    status = office.get(f"/api/applications/{app_id}").json()
    assert status["active"] and all(p["status"] == "live" for p in status["products"])
    steps = [s["step"] for s in status["timeline"]]
    assert "activated" in steps and "documents_erased" in steps
    assert not any(d["uploaded"] for d in status["documents"].values())   # document details deleted once live
    assert status["kyc"]["decision"] == "PASS"                            # the result is kept


def test_install_needs_kyc_first(office):
    app_id, rec = chat_to_quote(office)
    verify_phone(office, app_id)
    office.post(f"/api/applications/{app_id}/accept")
    r = office.post(f"/api/backoffice/applications/{app_id[:6]}/installed", json={"product_id": rec["core"][0]["id"]},
                    headers=STAFF)
    assert r.status_code == 409


# ---------- 5. accepted orders are kept ----------

def test_accepted_orders_outlive_the_lead_retention(monkeypatch):
    from backend.app.advisor.engine import Advisor
    s = Store(retention_hours=72)
    lead, order = (s.create(Advisor(order_date=None).start("en")[0]) for _ in range(2))
    order.accepted = True
    later = store_module._now() + timedelta(hours=100)
    monkeypatch.setattr(store_module, "_now", lambda: later)
    s.purge_expired()
    assert s.get(lead.id) is None and s.get(order.id) is not None
    monkeypatch.setattr(store_module, "_now", lambda: later + timedelta(days=366))
    s.purge_expired()
    assert s.get(order.id) is None


def test_privacy_page_shows_the_order_retention(office):
    app_id, _ = chat_to_quote(office)
    assert office.get(f"/api/applications/{app_id}").json()["retention_days"] is None
    verify_phone(office, app_id)
    office.post(f"/api/applications/{app_id}/accept")
    assert office.get(f"/api/applications/{app_id}").json()["retention_days"] == 365


# ---------- 6. what they pay today ----------

def test_current_spend_is_kept_for_the_comparison_and_the_call(office):
    app_id, _ = chat_to_quote(office)
    assert office.post(f"/api/applications/{app_id}/plan", json={"current_spend": 2500}).json()["current_spend"] == 2500
    assert office.post(f"/api/applications/{app_id}/plan", json={"current_spend": -5}).status_code == 422
    row = office.get("/api/backoffice/applications", headers=STAFF).json()[0]
    assert "Rs 2,500" in row["summary"]
    assert office.post(f"/api/applications/{app_id}/plan", json={"current_spend": 0}).json()["current_spend"] is None


# ---------- 7. success metrics ----------

def test_success_metrics_have_a_baseline_and_a_target(office):
    metrics = office.get("/api/backoffice/stats", headers=STAFF).json()["metrics"]
    assert [m["id"] for m in metrics] == ["conversion", "days", "cost", "chases", "churn"]
    by_id = {m["id"]: m for m in metrics}
    assert by_id["conversion"]["before"] == "7.4%" and by_id["days"]["before"] == "17.6 days"
    assert all(m["target"] and m["app"] for m in metrics)


# ---------- 8. DigiLocker (demo) ----------

def test_digilocker_certificates_pass_the_same_checks(office):
    app_id, _ = chat_to_quote(office)
    verify_phone(office, app_id)
    office.post(f"/api/applications/{app_id}/accept")
    assert office.post(f"/api/applications/{app_id}/documents/gst_certificate/digilocker").status_code == 403  # consent
    office.post(f"/api/applications/{app_id}/consent", json={"purposes": ["kyc"]})
    for t in ("gst_certificate", "udyam_certificate"):
        r = office.post(f"/api/applications/{app_id}/documents/{t}/digilocker").json()
        assert r["ok"] and r["digilocker"]
    assert r["fields"]["udyam_number"].count("*") >= 4                      # masked like a photo's details
    for t in ("address_proof", "signatory_id"):
        upload(office, app_id, t)
    assert office.post(f"/api/applications/{app_id}/kyc").json()["decision"] == "PASS"
    assert office.post(f"/api/applications/{app_id}/documents/address_proof/digilocker").status_code == 404


def test_digilocker_has_nothing_for_an_owner_without_gst_or_udyam(office):
    r = office.post("/api/applications", json={"language": "en"}).json()
    office.post(f"/api/applications/{r['id']}/message", json={"slot": "gstin", "value": "none"})
    main.store.get(r["id"]).consent = main.Consent(["kyc"], "en")
    out = office.post(f"/api/applications/{r['id']}/documents/udyam_certificate/digilocker")
    assert out.status_code == 404 and "DigiLocker" in out.json()["detail"]

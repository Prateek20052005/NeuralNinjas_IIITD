"""The whole owner journey through the HTTP API, in scripted mode (no AI calls), with real OCR on the photos."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import main

DOCS = Path(__file__).resolve().parent.parent / "data" / "kyc_documents"
ANSWERS = {"gstin": "27XUIXG0767D1ZP", "gst_confirm": "yes", "segment": "mfg", "employees": "12", "sites": "1",
           "internet": "fibre", "need:machines": "4", "need:vehicles": "0", "need:firewall": "yes"}


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
    client.post(f"/api/applications/{app_id}/accept")
    client.post(f"/api/applications/{app_id}/consent", json={"purposes": ["kyc"]})
    docs = client.get(f"/api/applications/{app_id}").json()["documents"]
    assert {k for k, v in docs.items() if v["required"]} == {"address_proof", "signatory_id"}
    for doc_type in ("address_proof", "signatory_id"):
        assert upload(client, app_id, doc_type).json()["ok"]
    assert client.post(f"/api/applications/{app_id}/kyc").json()["decision"] == "PASS"


def test_mobile_only_plan_can_still_switch_extras(client):
    answers = {**ANSWERS, "gstin": "none", "segment": "micro", "city": "Pune", "employees": "3",
               "internet": "mobile", "need:billing_pos": "no", "need:whatsapp": "no"}
    r = client.post("/api/applications", json={"language": "en"}).json()
    app_id, out = r["id"], r
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": answers[out["question"]["slot"]]}).json()
    rec = out["recommendation"]
    assert [x["id"] for x in rec["core"]] == ["P07"] and rec["addons"]
    r = client.post(f"/api/applications/{app_id}/addons", json={"product_id": rec["addons"][0]["id"], "on": True})
    assert r.status_code == 200 and r.json()["quote"]["valid"]

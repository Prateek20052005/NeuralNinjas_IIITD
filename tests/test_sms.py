"""Real SMS for one-time codes (OTP_MODE=sms): MSG91 (India, DLT template) or Twilio. A stand-in replaces the
provider, so no real text is ever sent by the tests."""
import logging
import urllib.parse

import pytest

from backend.app import sms
from tests.test_api import chat_to_quote, client  # noqa: F401  (pytest fixture)

PHONE = "9876543210"


@pytest.fixture()
def outbox(monkeypatch):
    """Every request the app would send to the SMS provider, answered with a success."""
    sent = []

    def fake_post(url, data, headers):
        sent.append({"url": url, "data": data.decode(), "headers": headers})
        if "msg91" in url:
            return 200, '{"type":"success","request_id":"x"}'
        return 201, '{"sid":"SM123"}'
    monkeypatch.setattr(sms, "_post", fake_post)
    return sent


@pytest.fixture()
def msg91(monkeypatch):
    monkeypatch.setenv("OTP_MODE", "sms")
    monkeypatch.setenv("SMS_PROVIDER", "msg91")
    monkeypatch.setenv("MSG91_AUTH_KEY", "test-auth-key")
    monkeypatch.setenv("MSG91_TEMPLATE_ID", "tmpl-123")


def code_from(request) -> str:
    return urllib.parse.parse_qs(urllib.parse.urlparse(request["url"]).query)["otp"][0]


def test_msg91_sends_the_code_and_the_screen_never_sees_it(client, msg91, outbox):
    app_id, _ = chat_to_quote(client)
    out = client.post(f"/api/applications/{app_id}/phone", json={"phone": PHONE}).json()
    assert out == {"sent": True, "phone": "98****3210"}                       # no demo_code in SMS mode
    query = urllib.parse.parse_qs(urllib.parse.urlparse(outbox[0]["url"]).query)
    assert query["template_id"] == ["tmpl-123"] and query["mobile"] == ["919876543210"]
    assert outbox[0]["headers"]["authkey"] == "test-auth-key"
    code = code_from(outbox[0])
    verified = client.post(f"/api/applications/{app_id}/phone/verify", json={"code": code}).json()
    assert verified["verified"]


def test_twilio_sends_the_message_text(client, monkeypatch, outbox):
    monkeypatch.setenv("OTP_MODE", "sms")
    monkeypatch.setenv("SMS_PROVIDER", "twilio")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setenv("TWILIO_FROM", "+14155550100")
    app_id = client.post("/api/applications", json={"language": "hi"}).json()["id"]
    assert "demo_code" not in client.post(f"/api/applications/{app_id}/phone", json={"phone": PHONE}).json()
    form = urllib.parse.parse_qs(outbox[0]["data"])
    assert form["To"] == ["+919876543210"] and form["From"] == ["+14155550100"]
    assert "Accel Business" in form["Body"][0] and any(ch.isdigit() for ch in form["Body"][0])
    assert "कोड" in form["Body"][0]                                          # in the owner's language
    assert outbox[0]["url"].endswith("/Accounts/AC123/Messages.json")
    assert outbox[0]["headers"]["Authorization"].startswith("Basic ")


def test_a_failed_sms_costs_no_wait_and_can_be_retried(client, msg91, monkeypatch):
    app_id = client.post("/api/applications", json={"language": "en"}).json()["id"]
    monkeypatch.setattr(sms, "_post", lambda url, data, headers: (500, "down"))
    r = client.post(f"/api/applications/{app_id}/phone", json={"phone": PHONE})
    assert r.status_code == 503 and "try again" in r.json()["detail"]
    monkeypatch.setattr(sms, "_post", lambda url, data, headers: (200, '{"type":"success"}'))
    assert client.post(f"/api/applications/{app_id}/phone", json={"phone": PHONE}).status_code == 200   # no 30 s wait


def test_sms_mode_without_settings_fails_safe(client, monkeypatch, outbox):
    monkeypatch.setenv("OTP_MODE", "sms")
    monkeypatch.setenv("SMS_PROVIDER", "msg91")
    monkeypatch.delenv("MSG91_AUTH_KEY", raising=False)
    monkeypatch.delenv("MSG91_TEMPLATE_ID", raising=False)
    app_id = client.post("/api/applications", json={"language": "en"}).json()["id"]
    r = client.post(f"/api/applications/{app_id}/phone", json={"phone": PHONE})
    assert r.status_code == 503 and "demo_code" not in r.text and not outbox   # never falls back to showing it
    health = client.get("/api/health").json()
    assert health["otp_demo"] is False and health["sms"] == {"provider": "msg91", "ready": False}


def test_an_unknown_mode_is_treated_as_sms_not_demo(client, monkeypatch):
    monkeypatch.setenv("OTP_MODE", "production")
    monkeypatch.delenv("SMS_PROVIDER", raising=False)
    app_id = client.post("/api/applications", json={"language": "en"}).json()["id"]
    r = client.post(f"/api/applications/{app_id}/phone", json={"phone": PHONE})
    assert r.status_code == 503 and "demo_code" not in r.text


def test_resume_by_sms(client, msg91, outbox):
    sent = client.post("/api/resume", json={"phone": PHONE}).json()
    assert "demo_code" not in sent and code_from(outbox[0]).isdigit()


def test_the_code_and_full_number_are_never_logged(client, msg91, outbox, caplog):
    app_id = client.post("/api/applications", json={"language": "en"}).json()["id"]
    with caplog.at_level(logging.DEBUG):
        client.post(f"/api/applications/{app_id}/phone", json={"phone": PHONE})
    assert code_from(outbox[0]) not in caplog.text and PHONE not in caplog.text

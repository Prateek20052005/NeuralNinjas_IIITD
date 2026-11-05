"""Saved progress and the mobile number: one-time codes, encrypted saving across restarts, the number required to
accept a plan, and continuing a saved application on another phone."""
import pickle

import pytest
from cryptography.fernet import Fernet

from backend.app import main, otp
from backend.app.advisor.engine import Advisor
from backend.app.store import Store
from tests.test_api import ANSWERS, chat_to_quote, client, verify_phone  # noqa: F401  (pytest fixture)

PHONE = "9876543210"


# ---------- one-time codes ----------

def test_code_is_checked_once_and_only_its_hash_is_kept():
    record, code = otp.issue(None, PHONE, now=1000)
    assert code not in str(record) and len(code) == 6
    with pytest.raises(otp.OtpError) as e:
        otp.check(record, "000000" if code != "000000" else "111111", now=1001)
    assert e.value.code == "wrong"
    assert otp.check(record, code, now=1002) == PHONE
    with pytest.raises(otp.OtpError):
        otp.check(record, code, now=1003)                     # a used code can't be used again


def test_code_limits():
    record, code = otp.issue(None, PHONE, now=1000)
    with pytest.raises(otp.OtpError) as e:
        otp.issue(record, PHONE, now=1010)                    # too soon for a new code
    assert e.value.code == "wait" and e.value.seconds == 20
    with pytest.raises(otp.OtpError) as e:
        otp.check(record, code, now=1000 + otp.CODE_TTL_SECONDS + 1)
    assert e.value.code == "expired"
    record, _ = otp.issue(None, PHONE, now=1000)
    for _ in range(otp.MAX_TRIES - 1):
        with pytest.raises(otp.OtpError):
            otp.check(record, "x", now=1001)
    with pytest.raises(otp.OtpError) as e:
        otp.check(record, "x", now=1001)
    assert e.value.code == "too_many"
    record, _ = otp.issue(None, PHONE, now=2000)
    for i in range(otp.MAX_SENDS - 1):
        record, _ = otp.issue(record, PHONE, now=2000 + 31 * (i + 1))
    with pytest.raises(otp.OtpError) as e:
        otp.issue(record, PHONE, now=2500)
    assert e.value.code == "too_many" and e.value.seconds == 2000 + otp.SEND_WINDOW_SECONDS - 2500
    record, _ = otp.issue(record, PHONE, now=2000 + otp.SEND_WINDOW_SECONDS + 1)   # an hour later: not locked out
    assert record["sends"] == 1
    assert not otp.stale(record, now=2000 + otp.SEND_WINDOW_SECONDS + 2)
    assert otp.stale(record, now=2000 + 3 * otp.SEND_WINDOW_SECONDS)


# ---------- saved, encrypted, and gone when deleted ----------

KEY = Fernet.generate_key().decode()


@pytest.fixture()
def saved_store(tmp_path, monkeypatch):
    s = Store(state_dir=str(tmp_path), key=KEY)
    monkeypatch.setattr(main, "store", s)
    return s


def test_progress_survives_a_restart_and_is_encrypted(client, saved_store, tmp_path):
    app_id, rec = chat_to_quote(client)
    verify_phone(client, app_id)
    files = list(tmp_path.glob("*.app"))
    assert len(files) == 1
    raw = files[0].read_bytes()
    assert b"27XUIXG0767D1ZP" not in raw and PHONE.encode() not in raw   # nothing readable on disk
    restarted = Store(state_dir=str(tmp_path), key=KEY)        # a new server process, same key
    a = restarted.get(app_id)
    assert a and a.phone == PHONE and a.items == {p["id"]: p["quantity"] for p in rec["core"]}
    assert a.session.recommendation is not None and a.lock is not None


def test_a_tampered_file_is_never_read(saved_store, tmp_path):
    app = saved_store.create(Advisor(order_date=None).start("en")[0])
    f = tmp_path / f"{app.id}.app"
    f.write_bytes(Fernet(Fernet.generate_key()).encrypt(pickle.dumps({"evil": True})))   # signed with another key
    restarted = Store(state_dir=str(tmp_path), key=KEY)
    assert restarted.get(app.id) is None


def test_deleting_removes_the_saved_file(client, saved_store, tmp_path):
    app_id, _ = chat_to_quote(client)
    assert list(tmp_path.glob("*.app"))
    client.delete(f"/api/applications/{app_id}")
    assert not list(tmp_path.glob("*.app"))


def test_expired_applications_are_deleted_from_disk(tmp_path):
    s = Store(retention_hours=0, state_dir=str(tmp_path), key=KEY)
    s.create(Advisor(order_date=None).start("en")[0])
    s.purge_expired()
    assert not list(tmp_path.glob("*.app"))


def test_files_from_an_older_version_still_load(saved_store, tmp_path):
    app = saved_store.create(Advisor(order_date=None).start("en")[0])
    state = app.__getstate__()
    for newer in ("phone", "marketing_consent", "billing_months"):
        state.pop(newer)                                       # as saved before these fields existed
    old = object.__new__(type(app))
    old.__dict__.update(state)
    restored = pickle.loads(pickle.dumps(old))
    assert restored.phone is None and restored.marketing_consent is False and restored.billing_months == 1


# ---------- the mobile number ----------

def test_accepting_needs_a_verified_mobile_number(client):
    app_id, _ = chat_to_quote(client)
    r = client.post(f"/api/applications/{app_id}/accept")
    assert r.status_code == 409 and "mobile" in r.json()["detail"]
    code = client.post(f"/api/applications/{app_id}/phone", json={"phone": "+91 98765 43210"}).json()["demo_code"]
    assert client.post(f"/api/applications/{app_id}/phone/verify", json={"code": "000000" if code != "000000" else "1"}
                       ).status_code == 422
    out = client.post(f"/api/applications/{app_id}/phone/verify", json={"code": code, "marketing": True}).json()
    assert out["phone"] == "98****3210" and out["marketing_consent"] is True
    assert client.post(f"/api/applications/{app_id}/accept").json()["accepted"]
    status = client.get(f"/api/applications/{app_id}").json()
    assert status["phone"] == "98****3210" and PHONE not in str(status)


def test_marketing_is_off_unless_ticked(client):
    app_id, _ = chat_to_quote(client)
    code = client.post(f"/api/applications/{app_id}/phone", json={"phone": PHONE}).json()["demo_code"]
    assert client.post(f"/api/applications/{app_id}/phone/verify", json={"code": code}).json()["marketing_consent"] is False


def test_bad_numbers_are_refused(client):
    app_id, _ = chat_to_quote(client)
    assert client.post(f"/api/applications/{app_id}/phone", json={"phone": "12345"}).status_code == 422


# ---------- continue on another phone ----------

def test_continue_a_saved_chat_on_another_phone(client):
    r = client.post("/api/applications", json={"language": "hi"}).json()
    app_id = r["id"]
    client.post(f"/api/applications/{app_id}/message", json={"slot": "gstin", "value": "none"})
    verify_phone(client, app_id, phone="9123456780")             # "save my progress" mid-chat
    code = client.post("/api/resume", json={"phone": "9123456780", "lang": "hi"}).json()["demo_code"]
    snap = client.post("/api/resume/verify", json={"phone": "9123456780", "code": code, "lang": "hi"}).json()
    assert snap["id"] == app_id and snap["screen"] == "chat" and snap["lang"] == "hi"
    assert snap["question"]["slot"] == "existing"                # the next question, in Hindi
    assert [m["text"] for m in snap["messages"]][-1] == snap["question"]["text"]
    assert snap["phoneVerified"] and snap["phoneSaved"] == "91****6780"


def test_continue_after_the_plan_goes_to_the_plan(client):
    app_id, rec = chat_to_quote(client)
    verify_phone(client, app_id, phone="9000000001")
    code = client.post("/api/resume", json={"phone": "9000000001"}).json()["demo_code"]
    snap = client.post("/api/resume/verify", json={"phone": "9000000001", "code": code}).json()
    assert snap["screen"] == "plan" and snap["rec"]["core"] and snap["items"] == {p["id"]: p["quantity"] for p in rec["core"]}


def test_resume_never_tells_which_numbers_have_applications(client):
    sent = client.post("/api/resume", json={"phone": "9555555555"})
    assert sent.status_code == 200 and sent.json()["sent"]       # same answer as for a number we know
    code = sent.json()["demo_code"]
    r = client.post("/api/resume/verify", json={"phone": "9555555555", "code": code})
    assert r.status_code == 404 and "72" in r.json()["detail"]
    wrong = client.post("/api/resume/verify", json={"phone": "9555555555", "code": "123456"})
    assert wrong.status_code == 422


def test_two_quick_taps_save_cleanly(client, saved_store, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    app_id = client.post("/api/applications", json={"language": "en"}).json()["id"]
    msg = f"/api/applications/{app_id}/message"
    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(lambda _: client.post(msg, json={"slot": "gstin", "value": "none"}).status_code, range(8)))
    assert set(codes) == {200} and len(list(tmp_path.glob("*.app"))) == 1 and not list(tmp_path.glob("*.tmp"))
    assert Store(state_dir=str(tmp_path), key=KEY).get(app_id).session.profile.gstin_status == "none"


def test_unused_resume_codes_are_forgotten(client, monkeypatch):
    import time as _time
    for i in range(3):
        client.post("/api/resume", json={"phone": f"90000{i:05d}"})
    assert len(main.store.resume_codes) >= 3
    later = _time.time() + 2 * otp.SEND_WINDOW_SECONDS
    monkeypatch.setattr(otp.time, "time", lambda: later)
    main.store.purge_expired()
    assert not any(p.startswith("90000") for p in main.store.resume_codes)


def test_privacy_page_can_switch_offers_off(client):
    app_id, _ = chat_to_quote(client)
    assert client.post(f"/api/applications/{app_id}/marketing", json={"on": True}).status_code == 409   # no number yet
    code = client.post(f"/api/applications/{app_id}/phone", json={"phone": PHONE}).json()["demo_code"]
    client.post(f"/api/applications/{app_id}/phone/verify", json={"code": code, "marketing": True})
    st = client.get(f"/api/applications/{app_id}").json()
    assert st["phone_verified"] and st["marketing_consent"] is True and st["phone"] == "98****3210"
    assert client.post(f"/api/applications/{app_id}/marketing", json={"on": False}).json() == {"marketing_consent": False}
    st = client.get(f"/api/applications/{app_id}").json()
    assert st["marketing_consent"] is False and st["timeline"][-1]["step"] == "marketing_off"


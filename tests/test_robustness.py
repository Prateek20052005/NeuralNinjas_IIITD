"""Failure cases: the AI failing or misbehaving, bad input to the API, double taps and many owners at once."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.advisor.engine import Advisor
from backend.app.advisor.llm import LLMUnavailable
from tests.test_advisor import FakeLLM, NoLLM
from tests.test_api import ANSWERS, chat_to_quote

TODAY = date(2026, 7, 15)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main.advisor, "llm", NoLLM())
    return TestClient(main.app)


# ---------- the AI failing or misbehaving ----------

def test_ai_dying_mid_chat_falls_back_and_still_finishes():
    llm = FakeLLM({"extract": {"no_gstin": True}, "say": ""}, LLMUnavailable("RateLimitError"))
    adv = Advisor(llm=llm, order_date=TODAY)
    s, _ = adv.start("en")
    replies = iter(["we have no GST at all", "no, we are new", "a small bakery", "We are in Pune", "3 of us", "only one shop",
                    "we use a mobile hotspot", "fibre is available", "yes please", "yes please", "no thanks"])
    out = {"question": True}
    while out.get("question"):
        out = adv.handle(s, text=next(replies))
    assert out["recommendation"]["quote"]["valid"] and s.profile.city == "Pune"
    assert any(f.startswith("turn:") for f in s.fallbacks)


@pytest.mark.parametrize("junk", [
    {"extract": ["not", "a", "dict"], "say": 42},
    {"extract": {"employees": "lots", "sites": -3, "kind": "spaceship", "city": "", "needs": "all"}, "say": None},
    {"extract": {"employees": 10 ** 9, "machines": -1, "needs": {"cctv": "maybe", "laser": True}}},
    {},
])
def test_junk_from_the_ai_never_crashes_or_corrupts_the_profile(junk):
    adv = Advisor(llm=FakeLLM(junk), order_date=TODAY)
    s, _ = adv.start("en")
    adv.handle(s, text="hello there, tell me more")
    p = s.profile
    assert p.segment is None and p.employees is None and p.sites is None and p.needs.machines == 0


def test_ai_answer_never_states_a_price_or_asks_its_own_question():
    say = "CCTV lets you watch your shop from your phone. It costs ₹999 per month. Shall I add it?"
    adv = Advisor(llm=FakeLLM({"extract": {"no_gstin": True}, "say": say}), order_date=TODAY)
    s, _ = adv.start("en")
    out = adv.handle(s, text="no GST, but what does CCTV do?")
    text = " ".join(out["messages"])
    assert "watch your shop" in text and "₹" not in text and "Shall I" not in text


# ---------- bad input to the API ----------

def test_bad_requests_get_clear_errors_not_crashes(client):
    app_id = client.post("/api/applications", json={"language": "xx"}).json()["id"]
    assert client.get(f"/api/applications/{app_id}").json()["language"] == "en"       # unknown language -> English
    msg = f"/api/applications/{app_id}/message"
    assert client.post(msg, json={"text": "   "}).status_code == 422
    assert client.post(msg, json={}).status_code == 422
    assert client.post(msg, json={"slot": "need:laser", "value": "yes"}).status_code == 200   # not on screen: ignored
    assert client.post(msg, json={"slot": "nonsense", "value": "yes"}).status_code == 200
    r = client.post(msg, json={"text": "x" * 20000}).json()                              # a giant paste is cut, not sent
    assert r["question"]["slot"] == "gstin"
    assert client.post("/api/applications/not-a-real-id/message", json={"text": "hi"}).status_code == 404
    assert client.post(f"/api/applications/{app_id}/accept").status_code == 409          # no quote yet
    assert client.post(f"/api/applications/{app_id}/addons", json={"product_id": "P01", "on": True}).status_code == 409


def test_upload_edge_cases(client):
    app_id, _ = chat_to_quote(client)
    client.post(f"/api/applications/{app_id}/consent", json={"purposes": ["kyc"]})
    up = f"/api/applications/{app_id}/documents"
    assert client.post(f"{up}/gst_certificate", files={"file": ("a.png", b"", "image/png")}).status_code == 415
    assert client.post(f"{up}/passport", files={"file": ("a.png", b"x", "image/png")}).status_code == 404
    big = b"\x89PNG" + b"0" * (main.MAX_UPLOAD_BYTES + 10)
    assert client.post(f"{up}/gst_certificate", files={"file": ("a.png", big, "image/png")}).status_code == 413
    res = client.post(f"/api/applications/{app_id}/kyc").json()                          # nothing uploaded yet
    assert res["decision"] == "INCOMPLETE"


def test_extra_switched_on_at_the_suggested_quantity(client):
    r = client.post("/api/applications", json={"language": "en"}).json()
    app_id, out = r["id"], r
    answers = {**ANSWERS, "gstin": "none", "segment": "multi", "city": "Pune", "employees": "20", "sites": "4",
               "need:central_management": "no", "need:cctv": "no", "need:toll_free": "no"}
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": answers[out["question"]["slot"]]}).json()
    extra = next(x for x in out["recommendation"]["addons"] if x["quantity"] > 1)
    q = client.post(f"/api/applications/{app_id}/addons", json={"product_id": extra["id"], "on": True}).json()["quote"]
    line = next(x for x in q["lines"] if x["product_id"] == extra["id"])
    assert line["quantity"] == extra["quantity"]


# ---------- double taps and many owners at once ----------

def test_double_tap_answers_only_one_question(client):
    app_id = client.post("/api/applications", json={"language": "en"}).json()["id"]
    msg = f"/api/applications/{app_id}/message"
    client.post(msg, json={"slot": "gstin", "value": "none"})
    client.post(msg, json={"slot": "existing", "value": "no"})
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: client.post(msg, json={"slot": "segment", "value": "micro"}), range(4)))
    out = client.post(msg, json={"slot": "city", "value": "Pune"}).json()
    assert out["question"]["slot"] == "employees"


def test_twenty_owners_chatting_at_the_same_time(client):
    with ThreadPoolExecutor(10) as pool:
        results = list(pool.map(lambda _: chat_to_quote(client), range(20)))
    assert len({app_id for app_id, _ in results}) == 20
    assert all(rec["quote"]["valid"] for _, rec in results)


# ---------- lessons from the live AI run (scripts/eval_advisor.py ai) ----------

def test_plain_no_to_gst_never_needs_the_ai():
    llm = FakeLLM()   # any AI call would fail this test with LLMUnavailable -> fallback note
    adv = Advisor(llm=llm, order_date=TODAY)
    for lang, text in [("mr", "नाही"), ("mr", "GST नाही"), ("en", "none"), ("hi", "nahi hai")]:
        s, _ = adv.start(lang)
        adv.handle(s, text=text)
        assert s.profile.gstin_status == "none" and not s.fallbacks, (lang, text)


def test_owners_words_beat_the_ai_on_kind_of_business():
    adv = Advisor(llm=FakeLLM({"extract": {"kind": "prof"}, "say": ""}), order_date=TODAY)
    s, _ = adv.start("hi")
    adv.handle(s, slot="gstin", value="none")
    adv.handle(s, slot="existing", value="no")
    adv.handle(s, text="मेरी दवाई की दुकान है")
    assert s.profile.segment == "micro"


def test_when_the_ai_understands_nothing_the_owner_still_hears_why():
    adv = Advisor(llm=FakeLLM({"extract": {}, "say": ""}), order_date=TODAY)
    s, _ = adv.start("en")
    out = adv.handle(s, text="asdf qwerty")
    assert "valid GST number" in out["messages"][0]


def test_ai_explanation_in_the_wrong_language_is_replaced_by_our_template():
    english = {"summary": "This plan suits your shop.", "reasons": {"P01": "Fast internet."}, "notes": []}
    adv = Advisor(llm=FakeLLM(english), order_date=TODAY)   # taps need no AI: the only call is the explanation
    s, _ = adv.start("hi")
    for slot, value in [("gstin", "none"), ("existing", "no"), ("segment", "micro"), ("city", "Pune"), ("employees", 2), ("sites", 1),
                        ("current", "home"), ("internet", "fibre"), ("need:billing_pos", "no"), ("need:whatsapp", "no"), ("need:cctv", "no")]:
        out = adv.handle(s, slot=slot, value=value)
    rec = out["recommendation"]
    assert rec["summary"] is None and all(re.search("[ऀ-ॿ]", x["reason"]) for x in rec["core"])

"""The smaller bugs from the audit: shop vs staff counts, GST on the setup fee, the office mobile line, the AI summary
and optional extras, GST-only questions for owners without GST, and the last line of a mobile-only plan."""
from datetime import date

import pytest

from backend.app.advisor.engine import Advisor
from backend.app.advisor.flow import Profile, apply_answer, next_slot
from backend.app.advisor.parse import kind_of_business, shop_count
from backend.app.catalogue import Business
from backend.app.quote import build_quote, with_gst
from backend.app.recommend import Needs, recommend
from tests.test_advisor import FakeLLM
from tests.test_api import ANSWERS, client  # noqa: F401  (pytest fixture)

TODAY = date(2026, 7, 15)


# ---------- staff count is not a shop count ----------

@pytest.mark.parametrize("text", ["one shop, 4 staff", "medicine shop, four of us work here",
                                  "दवाई की दुकान है, 4 लोग काम करते हैं, एक ही दुकान", "kirana store with 6 people",
                                  "salon, 5 staff"])
def test_staff_in_the_same_message_is_not_a_chain(text):
    assert kind_of_business(text) == "micro"


@pytest.mark.parametrize("text,n", [("we have 4 shops", 4), ("kapdon ki 6 dukaanein", 6), ("चार दुकानें हैं", 4),
                                    ("ek hi dukan", 1), ("3 stores in Pune", 3)])
def test_shop_counts_are_still_read(text, n):
    assert shop_count(text) == n
    assert kind_of_business(text) == ("multi" if n >= 3 else "micro")


# ---------- GST on the setup fee ----------

def test_setup_fee_is_shown_with_gst():
    q = build_quote({"P01": 1, "P07": 2, "P19": 1, "P23": 2}, Business("micro", 1, 4), TODAY, setup_months=6)
    assert q.setup_due > 0 and q.setup_due_with_gst == with_gst(q.setup_due)
    assert q.setup_gst == round(q.setup_due * 0.18)
    assert q.setup_monthly * 6 >= q.setup_due_with_gst                       # instalments add up to the GST total


# ---------- office mobile line ----------

def test_offices_get_the_cheaper_mobile_line_and_chains_the_roaming_one():
    office = recommend(Business("prof", 1, 10, 1, "active"), Needs(), TODAY).items()
    chain = recommend(Business("multi", 1, 20, 4, "active"), Needs(), TODAY).items()
    assert "P07" in office and "P08" not in office
    assert "P08" in chain


# ---------- owners without GST aren't asked about GST-only products ----------

def _questions(gst: str, segment: str) -> list[str]:
    p = Profile(language="en")
    apply_answer(p, "gstin", "none" if gst == "none" else "27XUIXG0767D1ZP")
    if p.gstin:
        apply_answer(p, "gst_confirm", "yes")
    p.existing_customer = False
    p.segment, p.employees, p.sites, p.current_tools = segment, 5, 1, "home"
    apply_answer(p, "city", "Pune")
    apply_answer(p, "internet", "fibre")
    asked = []
    while (slot := next_slot(p)):
        asked.append(slot)
        apply_answer(p, slot, "2" if slot in ("need:machines", "need:vehicles") else "yes")
    return asked


def test_no_gst_owners_are_not_asked_about_whatsapp_phone_lines_or_machines():
    assert "need:whatsapp" not in _questions("none", "micro")
    assert "need:phone_system" not in _questions("none", "prof")
    assert "need:machines" not in _questions("none", "mfg")
    assert "need:firewall" in _questions("none", "mfg")                     # antivirus stands in, so still asked
    assert "need:whatsapp" in _questions("active", "micro")                 # GST owners are still asked


# ---------- the AI summary never presents an extra as included ----------

def test_summary_naming_a_switched_off_extra_is_not_used():
    p = Profile(language="en", gstin_status="none", segment="micro", city="Pune", city_tier=1, employees=3, sites=1)
    rec = recommend(Business("micro", 1, 3), Needs(), TODAY)
    extra = __import__("backend.app.catalogue", fromlist=["load_catalogue"]).load_catalogue()[rec.addons[0].product_id]
    bad = {"summary": f"Your plan has fast internet, mobile lines and {extra.name} for your shop.",
           "reasons": {}, "notes": []}
    good = {"summary": "Your plan keeps payments and calls running all day in your shop.", "reasons": {}, "notes": []}
    s = Advisor(llm=FakeLLM(bad)).start("en")[0]
    s.profile = p
    assert "summary" not in Advisor(llm=FakeLLM(bad))._ai_explain(s, rec, {"reasons": {}, "notes": []})
    assert Advisor(llm=FakeLLM(good))._ai_explain(s, rec, {"reasons": {}, "notes": []})["summary"] == good["summary"]


# ---------- mobile-only plans ----------

def test_the_last_mobile_line_gives_the_right_message(client):
    answers = {**ANSWERS, "gstin": "none", "segment": "micro", "city": "Pune", "employees": "3",
               "current": "mobile", "internet": "mobile", "need:billing_pos": "no", "need:cctv": "no"}
    r = client.post("/api/applications", json={"language": "en"}).json()
    app_id, out = r["id"], r
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": answers[out["question"]["slot"]]}).json()
    assert [x["id"] for x in out["recommendation"]["core"]] == ["P07"]
    r = client.post(f"/api/applications/{app_id}/addons", json={"product_id": "P07", "on": False})
    assert r.status_code == 422 and "last mobile line" in r.json()["detail"] and "internet" not in r.json()["detail"]

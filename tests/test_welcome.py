"""Welcome offer for first-time customers, and pay-ahead billing (every 3, 6 or 12 months).

Rules (pricing_settings.json): setup free for small orders (< Rs 6,900/month), 30% off for large, 40% off from
Rs 15,900/month; 15% off the first 3 months (monthly or quarterly billing) or the first half-yearly / yearly bill, once.
The welcome months may go below the catalogue minimum; pay-ahead savings and chat discounts may not.
"""
from datetime import date

import pytest

from backend.app.catalogue import Business
from backend.app.customers import is_existing_customer
from backend.app.quote import build_quote, with_gst
from tests.test_api import ANSWERS, client, verify_phone  # noqa: F401  (pytest fixture)

TODAY = date(2026, 7, 15)
SHOP = ({"P01": 1, "P07": 2, "P19": 1}, Business("micro", 1, 3))                            # ~Rs 2,546/month
CLINIC = ({"P02": 1, "P08": 2, "P16": 10, "P20": 10, "P09": 1, "P12": 2, "P17": 1}, Business("prof", 1, 10, 1, "active"))
FACTORY = ({"P05": 2, "P08": 6, "P16": 15, "P21": 1, "P24": 10, "P11": 1}, Business("mfg", 1, 40, 1, "active"))


def quote(case, **kw):
    items, biz = case
    return build_quote(items, biz, TODAY, **kw)


@pytest.mark.parametrize("case,size,setup_off", [(SHOP, "small", 100), (CLINIC, "large", 30), (FACTORY, "very_large", 40)])
def test_setup_offer_depends_on_order_size(case, size, setup_off):
    q = quote(case, first_time=True)
    assert q.welcome["size"] == size and q.welcome["setup_off_pct"] == setup_off
    assert q.setup_discount == round(q.setup_total * setup_off / 100) and q.setup_due == q.setup_total - q.setup_discount


def test_fifteen_percent_off_the_first_three_months_may_go_below_the_floor():
    q = quote(SHOP, first_time=True)
    assert q.welcome["period_months"] == 3 and q.welcome["months_pct"] == 15
    assert q.welcome["per_month_with_gst"] == with_gst(round(q.monthly_total * 0.85))
    assert q.welcome["per_month_with_gst"] < with_gst(q.floor_total)          # a time-limited promotion
    assert q.monthly_with_gst == quote(SHOP).monthly_with_gst                  # from month 4: the normal price


@pytest.mark.parametrize("months,saving", [(3, 2), (6, 4), (12, 8)])
def test_paying_ahead_saves_and_never_goes_below_the_floor(months, saving):
    q = quote(SHOP, billing_months=months)
    option = next(o for o in q.billing_options if o["months"] == months)
    assert q.billing_months == months and option["saving_pct"] == pytest.approx(saving, abs=0.1)
    assert q.bill_with_gst == option["bill_with_gst"] and option["per_month_with_gst"] >= with_gst(q.floor_total)
    at_floor = quote(SHOP, contract_months=24, billing_months=months)          # already at the catalogue minimum
    assert all(o["saving_pct"] == 0 for o in at_floor.billing_options)


@pytest.mark.parametrize("months,period", [(1, 3), (3, 3), (6, 6), (12, 12)])
def test_welcome_covers_three_months_or_the_first_long_bill_once(months, period):
    q = quote(SHOP, first_time=True, billing_months=months)
    assert q.welcome["period_months"] == period
    assert q.welcome["first_bill_with_gst"] == pytest.approx(q.bill_with_gst * 0.85, abs=2 * months)   # 15% off, once
    assert q.bill_with_gst == quote(SHOP, billing_months=months).bill_with_gst                       # later bills: normal


def test_billing_never_longer_than_the_contract():
    airfiber = ({"P04": 1, "P07": 2}, Business("micro", 1, 3))                 # 6-month contract
    assert [o["months"] for o in quote(airfiber).billing_options] == [1, 3, 6]
    mobile_only = ({"P07": 2}, Business("micro", 1, 3))                        # 1-month contract
    assert [o["months"] for o in quote(mobile_only).billing_options] == [1]
    assert quote(airfiber, billing_months=12).billing_months == 1             # not offered: monthly


def test_existing_customers_get_no_welcome_offer():
    q = quote(SHOP)
    assert q.welcome is None and q.setup_discount == 0 and q.setup_due == q.setup_total
    assert is_existing_customer("27ZGXXB2827W1Z6")                              # with Accel already (our records)
    assert not is_existing_customer("27XUIXG0767D1ZP") and not is_existing_customer(None)


def test_chat_discount_stacks_with_the_welcome_offer():
    plain, haggled = quote(SHOP, first_time=True), quote(SHOP, first_time=True, discount_pct=10)
    assert haggled.welcome["per_month_with_gst"] < plain.welcome["per_month_with_gst"]
    assert haggled.monthly_total >= haggled.floor_total                        # the chat discount keeps the floor


# ---------- through the chat ----------

def chat(client, answers):
    r = client.post("/api/applications", json={"language": "en"}).json()
    app_id, out = r["id"], r
    while out.get("question"):
        out = client.post(f"/api/applications/{app_id}/message", json={"text": answers[out["question"]["slot"]]}).json()
    return app_id, client.post(f"/api/applications/{app_id}/plan", json={}).json()


SHOP_ANSWERS = {**ANSWERS, "gstin": "none", "segment": "micro", "city": "Pune", "employees": "3",
                "need:billing_pos": "yes", "need:whatsapp": "no", "need:cctv": "no"}


@pytest.mark.parametrize("answer,offer", [("no, we are new", True), ("yes, we already use Accel", False)])
def test_owners_without_gst_are_asked_once(client, answer, offer):
    app_id, plan = chat(client, {**SHOP_ANSWERS, "existing": answer})
    assert bool(plan["quote"]["welcome"]) is offer
    asked = client.get(f"/api/applications/{app_id}").json()["profile"]["existing_customer"]
    assert asked is (not offer)


def test_gstin_of_an_existing_customer_gets_no_offer_without_being_asked(client):
    answers = {**SHOP_ANSWERS, "gstin": "27ZGXXB2827W1Z6", "gst_confirm": "yes"}
    answers.pop("existing")                                                     # must not be asked
    _, plan = chat(client, answers)
    assert plan["quote"]["welcome"] is None


def test_billing_choice_is_saved_and_recorded(client):
    app_id, plan = chat(client, {**SHOP_ANSWERS, "existing": "no"})
    url = f"/api/applications/{app_id}/plan"
    assert client.post(url, json={"billing_months": 2}).status_code == 422
    yearly = client.post(url, json={"billing_months": 12}).json()["quote"]
    assert yearly["billing_months"] == 12 and yearly["welcome"]["period_months"] == 12
    verify_phone(client, app_id)   # accepting needs a verified mobile number
    accepted = client.post(f"/api/applications/{app_id}/accept").json()
    step = next(s for s in accepted["timeline"] if s["step"] == "quote_accepted")
    assert step["billing_months"] == 12 and step["first_time"] is True and step["setup_due"] == 0

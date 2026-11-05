"""Staff back office: statistics, customers, and the conversion predictor (which leads to call first)."""
import json

import pytest

from backend.app import main
from backend.app.predictor import WORTH_RETRYING, leads_to_call, model
from tests.test_api import chat_to_quote, client, verify_phone  # noqa: F401  (pytest fixture)

HEADERS = {"x-admin-key": "k"}


@pytest.fixture()
def staff(client, monkeypatch):
    monkeypatch.setenv("BACKOFFICE_KEY", "k")
    main._warm_predictor()          # tests don't wait for the background start-up
    return client


# ---------- the predictor ----------

def test_predictor_ranks_better_than_chance_on_leads_it_never_saw():
    m = model().metrics
    assert m["auc"] >= 0.7 and m["top10_activated_pct"] >= 2 * m["base_activated_pct"]
    assert m["test_leads"] == 1000 and m["leads"] == 5000


def test_predictor_does_not_use_language_or_anything_known_only_later():
    m = model()
    used = {name for name, _ in m.names}
    assert "preferred_language" not in used
    assert not used & {"stage_reached", "drop_reason", "outcome", "days_lead_to_activation", "contacted_date"}


def test_reasons_only_name_facts_true_of_the_lead():
    for lead in leads_to_call(200):
        words = " ".join(lead["up"] + lead["down"])
        if lead["segment"] != "Professional offices":
            assert "professional offices" not in words
        if "has GST" in lead["up"]:
            assert "no GST" not in words


def test_leads_to_call_are_retryable_and_best_first():
    leads = leads_to_call(100)
    assert len(leads) == 100 and all(lead["drop_reason"] in WORTH_RETRYING for lead in leads)
    scores = [lead["score"] for lead in leads]
    assert scores == sorted(scores, reverse=True) and all(0 < s < 1 for s in scores)


# ---------- the endpoints ----------

def test_back_office_needs_the_key(staff):
    for path in ("stats", "customers", "leads", "applications"):
        assert staff.get(f"/api/backoffice/{path}").status_code == 401
        assert staff.get(f"/api/backoffice/{path}", headers={"x-admin-key": "wrong"}).status_code == 401


def test_stats_customers_and_scores(staff):
    open_id, _ = chat_to_quote(staff)                       # one application still open
    bought_id, _ = chat_to_quote(staff)                     # one customer
    verify_phone(staff, bought_id, phone="9812345678")
    staff.post(f"/api/applications/{bought_id}/accept")

    stats = staff.get("/api/backoffice/stats", headers=HEADERS).json()
    funnel = {f["stage"]: f["count"] for f in stats["funnel"]}
    assert funnel["Got a plan"] >= 2 and funnel["Accepted the plan"] >= 1
    assert stats["money"]["monthly_with_gst"] > 0 and stats["history"]["funnel"][0]["count"] == 5000
    assert stats["history"]["funnel"][-1] == {"stage": "Activated", "count": 368}
    assert stats["predictor"]["auc"] >= 0.7

    customers = staff.get("/api/backoffice/customers", headers=HEADERS).json()
    mine = next(c for c in customers if c["ref"] == bought_id[:6].upper())
    assert mine["phone"] == "98****5678" and "9812345678" not in json.dumps(customers)
    assert mine["plan"] and mine["monthly_with_gst"] > 0
    assert all(c["ref"] != open_id[:6].upper() for c in customers)   # only people who accepted

    apps = staff.get("/api/backoffice/applications", headers=HEADERS).json()
    still_open = next(r for r in apps if r["id"] == open_id[:6])
    assert 0 < still_open["conversion"]["score"] < 1


def test_leads_endpoint(staff):
    out = staff.get("/api/backoffice/leads?limit=10", headers=HEADERS).json()
    assert len(out["leads"]) == 10 and out["model"]["auc"] >= 0.7
    assert {"score", "up", "down", "now", "drop_reason"} <= set(out["leads"][0])

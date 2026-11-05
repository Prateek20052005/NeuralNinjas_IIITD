"""What sells together: Apriori-style rules per kind of business, used to order a plan's extras and say how often
similar businesses chose each. They never add a product or change a price."""
from datetime import date

import pytest

from backend.app import bundles
from backend.app.bundles import MIN_BOTH, MIN_LIFT, MIN_WITH, SHOW_FROM_PCT, likelihood, rank_extras, top_rules
from backend.app.catalogue import Business, check_bundle
from backend.app.recommend import Needs, recommend

TODAY = date(2026, 7, 15)


def test_rules_are_learned_from_the_368_customers_per_kind_of_business():
    kinds = bundles._by_kind()
    assert set(kinds) == {"micro", "prof", "multi", "mfg"}
    assert sum(k.customers for k in kinds.values()) == 368


def test_without_a_strong_rule_it_is_the_share_of_that_kind_of_business():
    k = bundles._by_kind()["micro"]
    seen = likelihood("micro", set(), "P19")
    assert seen == {"pct": round(100 * k.has["P19"] / k.customers), "with": None, "lift": 1.0}


def test_a_rule_needs_enough_customers_and_a_real_lift():
    for rule in top_rules(per_kind=50):
        assert rule["customers"] >= MIN_WITH and rule["lift"] >= MIN_LIFT
    k = bundles._by_kind()["mfg"]
    seen = likelihood("mfg", {"P24"}, "P20")                      # machine sensors -> endpoint security
    assert seen["with"] == "P24" and k.pairs[("P24", "P20")] >= MIN_BOTH
    assert seen["pct"] > round(100 * k.has["P20"] / k.customers)  # higher than for factories overall


def test_extras_come_most_likely_first():
    ranked = rank_extras("prof", {"P02", "P08", "P16", "P20"}, ["P09", "P14", "P17", "P11", "P12"])
    pcts = [seen["pct"] for _, seen in ranked]
    assert pcts == sorted(pcts, reverse=True) and {pid for pid, _ in ranked} == {"P09", "P14", "P17", "P11", "P12"}


@pytest.mark.parametrize("biz", [Business("micro", 1, 3), Business("prof", 1, 10, 1, "active"),
                                 Business("multi", 1, 20, 4, "active"), Business("mfg", 1, 30, 1, "active")])
def test_plan_extras_are_ordered_and_only_meaningful_numbers_are_shown(biz):
    rec = recommend(biz, Needs(machines=4) if biz.segment == "mfg" else Needs(), TODAY)
    shown = [p.popularity["pct"] for p in rec.addons if p.popularity]
    assert shown == sorted(shown, reverse=True) and all(pct >= SHOW_FROM_PCT for pct in shown)
    full = rec.tiers()["full"]
    assert all(c.ok for c in check_bundle(full, biz).values())       # ordering never breaks the catalogue rules


def test_the_back_office_lists_what_sells_together(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app import main
    monkeypatch.setenv("BACKOFFICE_KEY", "k")
    rules = TestClient(main.app).get("/api/backoffice/stats", headers={"x-admin-key": "k"}).json()["sells_together"]
    assert rules and {r["kind"] for r in rules} == {"micro", "prof", "multi", "mfg"}
    assert all(r["pct"] > r["usual_pct"] for r in rules)

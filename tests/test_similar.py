"""Businesses like yours: the 20 most similar past customers shape per-person quantities and the extras' numbers."""
import statistics
from datetime import date

import pytest

from backend.app.catalogue import Business, check_bundle
from backend.app.recommend import Needs, recommend
from backend.app.similar import K, MIN_HAVING, PER_PERSON, neighbours, quantity, share

TODAY = date(2026, 7, 15)
SHOP = Business("micro", 1, 3)
OFFICE = Business("prof", 1, 10, 1, "active")


def test_neighbours_are_the_same_kind_and_close_in_size():
    near = neighbours(OFFICE)
    assert len(near) == K and all(c.kind == "prof" for c in near)
    assert 5 <= statistics.median(c.employees for c in near) <= 20          # a 10-person office's peers


def test_quantities_follow_size_and_never_exceed_the_team():
    small, big = Business("prof", 1, 8, 1, "active"), Business("prof", 1, 60, 1, "active")
    for pid in ("P16", "P20", "P08"):
        q_small, q_big = quantity(neighbours(small), pid, small), quantity(neighbours(big), pid, big)
        if q_small and q_big:
            assert q_small <= q_big                                         # bigger team, at least as many
        for biz, q in ((small, q_small), (big, q_big)):
            assert q is None or 1 <= q <= biz.employees


def test_needs_enough_similar_buyers_and_only_per_person_products():
    near = neighbours(SHOP)
    assert quantity(near, "P01", SHOP) is None                              # one per site: the plain rule
    rare = [pid for pid in PER_PERSON if sum(pid in c.items for c in near) < MIN_HAVING]
    assert all(quantity(near, pid, SHOP) is None for pid in rare)


def test_the_owners_own_answer_always_wins():
    rec = recommend(Business("micro", 1, 12), Needs(mobile_lines=7, cctv=True, cameras=5), TODAY)
    items = {p.product_id: p.quantity for p in rec.core}
    assert items["P07"] == 7 and items["P23"] == 5


def test_extras_numbers_come_from_similar_businesses():
    rec = recommend(OFFICE, Needs(), TODAY)
    near = neighbours(OFFICE)
    for pick in rec.addons:
        if pick.popularity and not pick.popularity["with"]:
            assert pick.popularity["pct"] == share(near, pick.product_id)
    assert rec.similar == K


@pytest.mark.parametrize("biz", [SHOP, Business("micro", 1, 12), OFFICE, Business("prof", 1, 40, 1, "active"),
                                 Business("multi", 1, 20, 4, "active"), Business("mfg", 1, 150, 1, "active")])
def test_plans_stay_valid(biz):
    rec = recommend(biz, Needs(machines=4) if biz.segment == "mfg" else Needs(), TODAY)
    for items in rec.tiers().values():
        assert all(c.ok for c in check_bundle(items, biz).values())
    assert rec.quote.valid

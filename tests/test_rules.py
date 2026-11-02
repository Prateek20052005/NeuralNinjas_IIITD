"""Rules, quote and recommender tests. Run: .venv/Scripts/python -m pytest -q"""
import csv
from datetime import date

import pytest

from backend.app.catalogue import DATA_DIR, Business, check_bundle, check_product, load_catalogue
from backend.app.quote import build_quote, toggle
from backend.app.recommend import Needs, recommend
from backend.app.reference import SEGMENT_CODE, business_types, city_tier

TODAY = date(2026, 7, 15)


def biz(segment="prof", tier=1, employees=10, sites=1, gst="active"):
    return Business(segment, tier, employees, sites, gst)


def all_ok(items, b):
    return all(c.ok for c in check_bundle(items, b).values())


# ---------- catalogue rules ----------

def test_catalogue_loads_25_products_with_mid_prices():
    cat = load_catalogue()
    assert len(cat) == 25
    assert cat["P02"].price == 1649  # (1499 + 1799) / 2


def test_tier_rule_1g_fibre_is_tier1_only():
    assert check_product("P03", biz(tier=1)).ok
    assert not check_product("P03", biz(tier=2)).ok


def test_employee_and_site_minimums():
    assert not check_product("P05", biz(employees=9)).ok
    assert check_product("P05", biz(employees=10)).ok
    assert not check_product("P10", biz(employees=40, sites=2)).ok
    assert check_product("P10", biz(employees=40, sites=3)).ok


@pytest.mark.parametrize("status,ok", [("active", True), ("inactive", False), ("none", False)])
def test_gstin_must_be_active(status, ok):
    assert check_product("P15", biz(gst=status)).ok is ok
    assert check_product("P01", biz(gst=status)).ok  # fibre never needs GST


def test_dependency_needs_internet_in_same_bundle():
    b = biz()
    assert not all_ok({"P09": 1}, b)
    assert all_ok({"P01": 1, "P09": 1}, b)
    assert not all_ok({"P04": 1, "P11": 1}, b)  # static IP needs fibre, not 5G AirFiber


# ---------- quote ----------

def test_quote_totals_setup_contract_and_eta():
    q = build_quote({"P01": 2, "P09": 2, "P23": 3}, biz(employees=5, sites=2), TODAY)
    assert q.valid
    assert q.monthly_total == 1099 * 2 + 549 * 2 + 249 * 3
    assert q.setup_total == 1500 * 2 + 1800 * 3  # setup fee x quantity
    assert q.contract_months == 12
    assert q.install_days == 5 and q.expected_live == date(2026, 7, 20)
    assert q.monthly_with_gst == q.monthly_total + round(q.monthly_total * 0.18)


def test_quote_reports_invalid_products_instead_of_hiding_them():
    q = build_quote({"P03": 1}, biz(tier=2), TODAY)
    assert not q.valid and "tier-2" in q.problems[0]


def test_contract_is_longest_minimum():
    q = build_quote({"P01": 1, "P21": 1}, biz(employees=12), TODAY)
    assert q.contract_months == 24


def test_toggle_off_internet_removes_dependent_addons():
    items, notes = toggle({"P01": 1, "P09": 1, "P22": 1, "P07": 2}, "P01", on=False)
    assert items == {"P07": 2}
    assert len(notes) == 2


# ---------- recommender: tricky cases ----------

def ids(rec):
    return {p.product_id for p in rec.core}


def test_tier2_never_gets_1g_fibre():
    rec = recommend(biz("prof", tier=2, employees=25), order_date=TODAY)
    assert "P03" not in ids(rec) and "P02" in ids(rec)
    assert any("tier-2" in n for n in rec.notes)


def test_no_gstin_owner_asking_for_whatsapp_gets_explanation():
    rec = recommend(biz("micro", tier=1, employees=3, gst="none"), Needs(whatsapp=True), TODAY)
    assert "P15" not in ids(rec)
    assert any("GST" in n for n in rec.notes)


def test_cancelled_gstin_blocks_gst_products():
    rec = recommend(biz("prof", tier=2, employees=13, gst="inactive"), Needs(phone_system=True), TODAY)
    assert "P12" not in ids(rec) and rec.quote.valid


def test_two_sites_cannot_get_sdwan():
    rec = recommend(biz("multi", employees=20, sites=2), Needs(central_management=True), TODAY)
    assert "P10" not in ids(rec)


def test_no_fibre_site_gets_5g_airfiber():
    rec = recommend(biz("micro", employees=2), Needs(fibre_available=False), TODAY)
    assert "P04" in ids(rec) and "P01" not in ids(rec)


def test_small_factory_without_gst_falls_back_to_plain_fibre():
    rec = recommend(biz("mfg", tier=1, employees=40, gst="none"), order_date=TODAY)
    assert ids(rec) & {"P01", "P02"} and not ids(rec) & {"P03", "P05", "P06"}


def test_owner_saying_no_is_respected():
    rec = recommend(biz("prof"), Needs(cloud_email=False, security=False), TODAY)
    assert not ids(rec) & {"P16", "P20"}


# ---------- recommender: every real lead ----------

def lead_businesses():
    gst_status = {}
    with open(DATA_DIR / "mock_gstin_registry.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            gst_status[r["gstin"]] = "active" if r["status"] == "Active" else "inactive"
    with open(DATA_DIR / "smb_leads.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            yield r["lead_id"], Business(SEGMENT_CODE[r["segment"]], int(r["city_tier"]), int(r["employee_count"]),
                                         int(r["num_sites"]), gst_status.get(r["gstin"], "none"))


def test_every_lead_gets_a_rule_passing_bundle_with_addons():
    for lead_id, b in lead_businesses():
        rec = recommend(b, order_date=TODAY)
        assert rec.quote.valid, (lead_id, rec.quote.problems)
        assert rec.core, lead_id
        with_addons = {**rec.items(), **{a.product_id: a.quantity for a in rec.addons}}
        assert all_ok(with_addons, b), lead_id


def test_reference_tables():
    assert business_types()["Dental clinic"] == "prof"
    assert city_tier("Nagpur") == 2 and city_tier("pune") == 1
    assert city_tier("Unknown town") == 2

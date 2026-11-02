"""Product catalogue and eligibility rules.

Every "can we sell this?" decision lives here, never in the AI. Rules come from
product_catalogue.csv and the dataset README:
  - available_city_tiers: tiers where the product is sold
  - min_employees, min_sites: product only offered at or above these sizes
  - requires_gstin = Y: needs a valid, ACTIVE GSTIN (Cancelled/Suspended count as not valid)
  - requires_one_of: at least one of these products must be in the same bundle
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

SEGMENTS = {
    "micro": "Micro retail & services",
    "prof": "Professional offices",
    "multi": "Small multi-site businesses",
    "mfg": "Small manufacturers",
}


INTERNET_LINES = frozenset({"P01", "P02", "P03", "P04", "P05", "P06"})  # fibre, 5G and leased lines


@dataclass(frozen=True)
class Product:
    id: str
    category: str
    name: str
    description: str
    unit: str
    price_min: int
    price_max: int
    setup_fee: int
    min_contract_months: int
    city_tiers: frozenset[int]
    min_employees: int
    min_sites: int
    requires_gstin: bool
    requires_one_of: frozenset[str]
    install_days: int
    target_segments: frozenset[str]

    @property
    def price(self) -> int:
        """Quoted monthly price per unit: middle of the catalogue range."""
        return round((self.price_min + self.price_max) / 2)


@dataclass
class Business:
    """What we know about the owner's business. gstin_status: 'active', 'inactive' (cancelled/suspended) or 'none'."""
    segment: str
    city_tier: int
    employees: int
    sites: int = 1
    gstin_status: str = "none"
    business_type: str = ""
    city: str = ""

    @property
    def has_active_gstin(self) -> bool:
        return self.gstin_status == "active"


@dataclass
class RuleCheck:
    product_id: str
    ok: bool
    reasons: list[str] = field(default_factory=list)  # plain-language reasons when not ok (English)
    codes: list[tuple[str, dict]] = field(default_factory=list)  # same reasons as (code, params) for translation


@lru_cache(maxsize=1)
def load_catalogue() -> dict[str, Product]:
    products = {}
    with open(DATA_DIR / "product_catalogue.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            products[r["product_id"]] = Product(
                id=r["product_id"],
                category=r["category"],
                name=r["product_name"],
                description=r["description"],
                unit=r["unit"],
                price_min=int(r["price_min_inr_per_month"]),
                price_max=int(r["price_max_inr_per_month"]),
                setup_fee=int(r["one_time_setup_inr"]),
                min_contract_months=int(r["min_contract_months"]),
                city_tiers=frozenset(int(t) for t in r["available_city_tiers"].split(";")),
                min_employees=int(r["min_employees"]),
                min_sites=int(r["min_sites"]),
                requires_gstin=r["requires_gstin"] == "Y",
                requires_one_of=frozenset(p for p in r["requires_one_of"].split("|") if p),
                install_days=int(r["typical_install_days"]),
                target_segments=frozenset(r["target_segments"].split(";")),
            )
    return products


def check_product(pid: str, biz: Business) -> RuleCheck:
    """Can this business buy this product at all (ignoring what else is in the bundle)?"""
    p = load_catalogue()[pid]
    reasons, codes = [], []
    if biz.city_tier not in p.city_tiers:
        reasons.append(f"{p.name} is not yet available in tier-{biz.city_tier} cities")
        codes.append(("tier", {"tier": biz.city_tier}))
    if biz.employees < p.min_employees:
        reasons.append(f"{p.name} is for businesses with {p.min_employees}+ employees")
        codes.append(("employees", {"n": p.min_employees}))
    if biz.sites < p.min_sites:
        reasons.append(f"{p.name} is for businesses with {p.min_sites}+ sites")
        codes.append(("sites", {"n": p.min_sites}))
    if p.requires_gstin and not biz.has_active_gstin:
        reasons.append(f"{p.name} needs an active GST registration")
        codes.append(("gstin", {}))
    return RuleCheck(pid, not reasons, reasons, codes)


def check_bundle(items: dict[str, int], biz: Business) -> dict[str, RuleCheck]:
    """Check every product in a bundle, including 'needs one of these in the same bundle' rules."""
    cat = load_catalogue()
    results = {}
    for pid in items:
        rc = check_product(pid, biz)
        needs = cat[pid].requires_one_of
        if needs and not needs & set(items):
            names = " or ".join(cat[n].name for n in sorted(needs))
            rc.ok = False
            rc.reasons.append(f"{cat[pid].name} works only together with {names}")
            rc.codes.append(("needs_one_of", {"needs": sorted(needs)}))
        results[pid] = rc
    return results


def eligible_products(biz: Business) -> list[str]:
    return [pid for pid in load_catalogue() if check_product(pid, biz).ok]

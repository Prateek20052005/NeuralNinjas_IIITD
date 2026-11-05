"""Businesses like yours: the past customers most similar to this owner, used for quantities and extras.

From the 368 activated customers in smb_leads.csv, the K most similar ones: same kind of business, then closest in
team size and number of sites (on a log scale, so 3 vs 6 people is as far apart as 30 vs 60), same city tier and same
GST status. Only what the chat already knows is compared; no names or numbers.

Quantities: per-person and per-device products (mobile lines, email seats, antivirus, phone channels) follow what
similar businesses bought for their size: the middle (median) of their "per person" ratios, times this owner's team
(cameras: per site). Only with at least MIN_HAVING similar businesses that bought the product; otherwise the plain
rule in recommend.py stays. One-per-site products (internet line, billing counter, Wi-Fi, backup router) already match
the number of sites in every past bundle, so they keep that rule. An owner's own answer ("5 cameras") always wins.
"""
from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass
from functools import lru_cache

from .catalogue import DATA_DIR, SEGMENTS, Business

K = 20                 # similar businesses to look at
MIN_HAVING = 5         # of them, how many must have bought a product before their quantities are used
PER_PERSON = {"P07", "P08", "P16", "P20", "P12"}   # mobile lines, email seats, antivirus, phone channels
PER_SITE = {"P23"}                                    # cameras
_CODE = {name: code for code, name in SEGMENTS.items()}


@dataclass(frozen=True)
class Customer:
    kind: str
    employees: int
    sites: int
    tier: int
    gst: bool
    items: dict[str, int]


@lru_cache(maxsize=1)
def customers() -> tuple[Customer, ...]:
    with open(DATA_DIR / "smb_leads.csv", encoding="utf-8") as f:
        return tuple(
            Customer(_CODE[r["segment"]], int(r["employee_count"]), int(r["num_sites"]), int(r["city_tier"]),
                     r["has_gstin"] == "Y",
                     {item.split("x")[0]: int(item.split("x")[1]) for item in r["bundle_products"].split(";")})
            for r in csv.DictReader(f) if r["outcome"] == "Activated" and r["bundle_products"])


def _distance(c: Customer, biz: Business) -> float:
    return (abs(math.log1p(c.employees) - math.log1p(biz.employees))
            + abs(math.log(c.sites) - math.log(max(biz.sites, 1)))
            + 0.5 * (c.tier != biz.city_tier) + 0.5 * (c.gst != biz.has_active_gstin))


def neighbours(biz: Business, k: int = K) -> list[Customer]:
    """The k past customers most like this business, from the same kind of business."""
    pool = [c for c in customers() if c.kind == biz.segment]
    return sorted(pool, key=lambda c: _distance(c, biz))[:k]


def share(near: list[Customer], pid: str) -> int | None:
    """% of the similar businesses that took this product."""
    return round(100 * sum(pid in c.items for c in near) / len(near)) if near else None


def quantity(near: list[Customer], pid: str, biz: Business) -> int | None:
    """How many similar businesses bought for their size, scaled to this one; None = not enough of them to say."""
    if pid not in PER_PERSON | PER_SITE:
        return None
    having = [c for c in near if pid in c.items]
    if len(having) < MIN_HAVING:
        return None
    size = (lambda c: c.sites) if pid in PER_SITE else (lambda c: c.employees)
    ratio = statistics.median(c.items[pid] / size(c) for c in having)
    mine = max(biz.sites, 1) if pid in PER_SITE else biz.employees
    qty = max(1, round(ratio * mine))
    return min(qty, biz.employees) if pid in PER_PERSON else qty   # never more seats or lines than people

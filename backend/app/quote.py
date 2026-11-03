"""Quote engine: one clear monthly price for a bundle.

Pricing rules (checked against all 368 activated bundles in smb_leads.csv):
  - monthly price per unit = middle of the catalogue range (past deals sat at ~48% of the range)
  - one-time setup = setup fee x quantity
  - contract length = the longest minimum contract of any product in the bundle
  - expected activation = longest install time in the bundle (installs run in parallel)

Our own pricing rule (a proposal, not taken from the data: past deals were not cheaper on longer contracts).
Prices never leave the catalogue range:
  - the shortest contract the bundle allows: middle of the range (as above)
  - 12 months, when the bundle allows less: a quarter of the way down the range
  - 24 months: the catalogue minimum. Acquiring a customer costs ~Rs 15,000, so a longer commitment is worth it.
The setup fee can be paid at once or spread over 6 or 12 months (same total, no interest, never past the contract).
A negotiated discount (see negotiate.py) comes off the monthly price before GST, never below the catalogue minimum.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from .catalogue import Business, check_bundle, load_catalogue

GST_RATE = 0.18  # catalogue prices exclude GST; shown separately so the total is honest
SETUP_SPREAD_CHOICES = (1, 6, 12)      # 1 = pay the setup fee at once


def min_contract(items: dict[str, int]) -> int:
    cat = load_catalogue()
    return max((cat[pid].min_contract_months for pid in items if pid in cat), default=1)


def contract_options(items: dict[str, int]) -> list[int]:
    """The bundle's own minimum, plus 12 and 24 months when those are longer."""
    low = min_contract(items)
    return sorted({low, *(m for m in (12, 24) if m > low)})


def price_position(contract: int, minimum: int) -> float:
    """Where in the catalogue range the price sits: 0.5 = middle (today's price), 0 = catalogue minimum."""
    if contract >= 24:
        return 0.0
    if contract > minimum:
        return 0.25
    return 0.5


def unit_price(p, position: float) -> int:
    return round(p.price_min + position * (p.price_max - p.price_min))


@dataclass
class QuoteLine:
    product_id: str
    name: str
    unit: str
    quantity: int
    unit_price: int
    price_range: tuple[int, int]
    monthly: int
    setup: int
    install_days: int


@dataclass
class Quote:
    lines: list[QuoteLine]
    monthly_total: int
    monthly_gst: int
    monthly_with_gst: int
    setup_total: int
    contract_months: int
    install_days: int
    expected_live: date
    valid: bool
    problems: list[str] = field(default_factory=list)
    setup_months: int = 1                 # 1 = setup fee paid at once
    setup_monthly: int = 0                # instalment when spread
    min_contract_months: int = 1
    contract_options: list[dict] = field(default_factory=list)   # [{"months", "monthly_with_gst"}]
    list_total: int = 0                   # monthly price before any negotiated discount (excl. GST)
    floor_total: int = 0                  # the same products at their catalogue minimum: the lowest possible price
    discount: int = 0                     # rupees off the monthly price (excl. GST)
    discount_pct: float = 0.0             # discount as a share of list_total


def build_quote(items: dict[str, int], biz: Business, order_date: date | None = None,
                contract_months: int | None = None, setup_months: int = 1, discount_pct: float = 0.0,
                _options: bool = True) -> Quote:
    """Price a bundle. items = {product_id: quantity}. Invalid products are reported, not silently priced.
    contract_months: the owner's choice (raised to the bundle's minimum); None = the minimum."""
    cat = load_catalogue()
    minimum = min_contract(items)
    contract = max(contract_months or minimum, minimum)
    position = price_position(contract, minimum)
    checks = check_bundle(items, biz)
    problems = [r for c in checks.values() for r in c.reasons]
    lines = []
    for pid, qty in items.items():
        if qty < 1:
            problems.append(f"{cat[pid].name}: quantity must be at least 1")
            continue
        p = cat[pid]
        price = unit_price(p, position)
        lines.append(QuoteLine(pid, p.name, p.unit, qty, price, (p.price_min, p.price_max),
                               price * qty, p.setup_fee * qty, p.install_days))
    list_total = sum(l.monthly for l in lines)
    floor_total = sum(cat[l.product_id].price_min * l.quantity for l in lines)
    discount = min(round(list_total * max(discount_pct, 0) / 100), list_total - floor_total)   # never below the floor
    monthly = list_total - discount
    gst = round(monthly * GST_RATE)
    install = max((l.install_days for l in lines), default=0)
    order_date = order_date or date.today()
    setup_total = sum(l.setup for l in lines)
    spread = setup_months if setup_months in SETUP_SPREAD_CHOICES and setup_months <= contract and setup_total else 1
    options = [{"months": m, "monthly_with_gst": build_quote(items, biz, order_date, m, discount_pct=discount_pct,
                                                             _options=False).monthly_with_gst}
               for m in contract_options(items)] if _options else []
    return Quote(
        lines=lines,
        monthly_total=monthly,
        monthly_gst=gst,
        monthly_with_gst=monthly + gst,
        setup_total=setup_total,
        contract_months=contract if lines else 0,
        install_days=install,
        expected_live=order_date + timedelta(days=install),
        valid=not problems,
        problems=problems,
        setup_months=spread,
        setup_monthly=math.ceil(setup_total / spread) if spread > 1 else 0,
        min_contract_months=minimum,
        contract_options=options,
        list_total=list_total,
        floor_total=floor_total,
        discount=discount,
        discount_pct=round(100 * discount / list_total, 1) if list_total else 0.0,
    )


def toggle(items: dict[str, int], pid: str, on: bool, qty: int = 1) -> tuple[dict[str, int], list[str]]:
    """Switch an add-on on or off. Turning off a product also drops anything that can't work without it.

    Returns the new items and a list of plain-language notes about what else changed.
    """
    cat = load_catalogue()
    items = dict(items)
    notes = []
    if on:
        items[pid] = max(qty, 1)
        return items, notes
    items.pop(pid, None)
    changed = True
    while changed:  # removing one product can orphan another
        changed = False
        for other in list(items):
            needs = cat[other].requires_one_of
            if needs and not needs & set(items):
                items.pop(other)
                notes.append(f"{cat[other].name} was also removed because it needs {cat[pid].name} or another internet line")
                changed = True
    return items, notes

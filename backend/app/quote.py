"""Quote engine: one clear monthly price for a bundle.

Pricing rules (checked against all 368 activated bundles in smb_leads.csv):
  - monthly price per unit = middle of the catalogue range (past deals sat at ~48% of the range)
  - one-time setup = setup fee x quantity
  - contract length = the longest minimum contract of any product in the bundle
  - expected activation = longest install time in the bundle (installs run in parallel)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .catalogue import Business, check_bundle, load_catalogue

GST_RATE = 0.18  # catalogue prices exclude GST; shown separately so the total is honest


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


def build_quote(items: dict[str, int], biz: Business, order_date: date | None = None) -> Quote:
    """Price a bundle. items = {product_id: quantity}. Invalid products are reported, not silently priced."""
    cat = load_catalogue()
    checks = check_bundle(items, biz)
    problems = [r for c in checks.values() for r in c.reasons]
    lines = []
    for pid, qty in items.items():
        if qty < 1:
            problems.append(f"{cat[pid].name}: quantity must be at least 1")
            continue
        p = cat[pid]
        lines.append(QuoteLine(pid, p.name, p.unit, qty, p.price, (p.price_min, p.price_max),
                               p.price * qty, p.setup_fee * qty, p.install_days))
    monthly = sum(l.monthly for l in lines)
    gst = round(monthly * GST_RATE)
    install = max((l.install_days for l in lines), default=0)
    order_date = order_date or date.today()
    return Quote(
        lines=lines,
        monthly_total=monthly,
        monthly_gst=gst,
        monthly_with_gst=monthly + gst,
        setup_total=sum(l.setup for l in lines),
        contract_months=max((cat[l.product_id].min_contract_months for l in lines), default=0),
        install_days=install,
        expected_live=order_date + timedelta(days=install),
        valid=not problems,
        problems=problems,
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

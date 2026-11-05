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

Billing: pay every month, or every 3, 6 or 12 months in advance for a small saving (pay_ahead_saving_pct), again never
below the catalogue minimum. Welcome offer for first-time customers (pricing_settings.json "welcome"):
  - setup fee: free for small orders, 30% off for large, 40% off for very large (order size = list monthly price)
  - 15% off the first 3 months (monthly or quarterly billing) or off the first half-yearly / yearly bill, once.
    It is a time-limited promotion, so this one may go below the catalogue minimum; everything else may not.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from .catalogue import Business, check_bundle, load_catalogue
from .negotiate import settings as price_settings

GST_RATE = 0.18  # catalogue prices exclude GST; shown separately so the total is honest
SETUP_SPREAD_CHOICES = (1, 6, 12)      # 1 = pay the setup fee at once
BILLING_CHOICES = (1, 3, 6, 12)        # pay every month, quarter, half-year or year


def with_gst(amount: int) -> int:
    return amount + round(amount * GST_RATE)


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
    billing_months: int = 1               # pay every 1, 3, 6 or 12 months
    billing_options: list[dict] = field(default_factory=list)    # [{"months", "saving_pct", "per_month_with_gst", "bill_with_gst"}]
    bill_with_gst: int = 0                # one regular bill for the chosen billing period
    setup_discount: int = 0               # welcome offer on the setup fee
    setup_due: int = 0                    # setup fee after the welcome offer
    welcome: dict | None = None           # first-time customers: the first-months offer (see module notes)


def build_quote(items: dict[str, int], biz: Business, order_date: date | None = None,
                contract_months: int | None = None, setup_months: int = 1, discount_pct: float = 0.0,
                billing_months: int = 1, first_time: bool = False, _options: bool = True) -> Quote:
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

    # pay ahead: every 3, 6 or 12 months (only within the contract), a small saving, never below the floor
    rules = price_settings()
    term = contract if lines else 1

    def per_month(months: int) -> int:
        pct = rules["pay_ahead_saving_pct"].get(months, 0) if months > 1 else 0
        return max(round(monthly * (1 - pct / 100)), min(floor_total, monthly))

    billing_options = [{"months": k, "saving_pct": round(100 * (monthly - per_month(k)) / monthly, 1) if monthly else 0.0,
                        "per_month_with_gst": with_gst(per_month(k)), "bill_with_gst": with_gst(per_month(k) * k)}
                       for k in BILLING_CHOICES if k <= max(term, 1)]
    billing = billing_months if any(o["months"] == billing_months for o in billing_options) else 1
    pay_month = per_month(billing)

    # welcome offer for first-time customers: setup by order size, and the first months (may go below the floor)
    welcome, setup_discount = None, 0
    if first_time and lines:
        w = rules["welcome"]
        size = ("very_large" if list_total >= w["very_large_order_from"]
                else "large" if list_total >= w["large_order_from"] else "small")
        setup_discount = round(setup_total * w["setup_off_pct"][size] / 100)
        period = max(w["first_months"], billing)          # first 3 months, or the first half-yearly / yearly bill
        first = round(pay_month * (1 - w["first_months_pct"] / 100))
        welcome = {"size": size, "setup_off_pct": w["setup_off_pct"][size], "months_pct": w["first_months_pct"],
                   "period_months": period, "per_month_with_gst": with_gst(first),
                   "first_bill_with_gst": with_gst(first * billing),
                   "saving_with_gst": with_gst(pay_month * period) - with_gst(first * period)}
    setup_due = setup_total - setup_discount
    spread = setup_months if setup_months in SETUP_SPREAD_CHOICES and setup_months <= contract and setup_due else 1
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
        setup_monthly=math.ceil(setup_due / spread) if spread > 1 else 0,
        min_contract_months=minimum,
        contract_options=options,
        list_total=list_total,
        floor_total=floor_total,
        discount=discount,
        discount_pct=round(100 * discount / list_total, 1) if list_total else 0.0,
        billing_months=billing,
        billing_options=billing_options,
        bill_with_gst=with_gst(pay_month * billing),
        setup_discount=setup_discount,
        setup_due=setup_due,
        welcome=welcome,
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

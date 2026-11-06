"""Success metrics (case key question 5): the 5 numbers that matter, the baseline from the sales-led quarter in
smb_leads.csv, the pilot target, and what the app shows so far. Targets are proposals for a 2-quarter pilot in 2-3
tier-1 cities (micro and professional offices first); change them here."""
from __future__ import annotations

import csv
import statistics
from datetime import date
from functools import lru_cache

from .catalogue import DATA_DIR

TARGETS = {
    "conversion": {"label": "Lead to activation", "target": "15% or more",
                   "why": "Owners finish in one sitting instead of waiting for a visit and a PDF quote"},
    "days": {"label": "Days from first contact to live", "target": "under 5 days (fibre and AirFiber plans)",
             "why": "Instant quote and KYC; only the install itself takes time"},
    "cost": {"label": "Cost to win a customer", "target": "under Rs 6,000 on app-led sales",
             "why": "No visit for simple plans; field force spends its time on multi-site and factory deals"},
    "chases": {"label": "Status calls from the customer", "target": "under 0.5 per customer",
               "why": "The tracker shows each product's ready-by date"},
    "churn": {"label": "Customers leaving within 6 months", "target": "20-30% lower than before",
              "why": "Right-sized plans, one bill, a price compared with what they pay today"},
}


@lru_cache(maxsize=1)
def baseline() -> dict:
    with open(DATA_DIR / "smb_leads.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    active = [r for r in rows if r["outcome"] == "Activated"]
    return {
        "conversion": f"{100 * len(active) / len(rows):.1f}%",
        "days": f"{statistics.mean(int(r['days_lead_to_activation']) for r in active):.1f} days",
        "cost": f"Rs {round(sum(float(r['acquisition_cost_inr'] or 0) for r in rows) / len(active), -2):,.0f}",
        "chases": f"{statistics.mean(int(r['customer_follow_up_calls'] or 0) for r in active):.1f} per customer",
        "churn": f"{100 * sum(r['churned_within_6_months'] == 'Y' for r in active) / len(active):.1f}%",
    }


def app_so_far(apps, booked_on, ready_by) -> dict:
    """What the live app shows (small numbers in a demo; the pilot measures them properly)."""
    started = len(apps)
    booked = [a for a in apps if booked_on(a)]
    days = [(ready_by(a) - date.fromisoformat(a.timeline[0]["at"][:10])).days for a in booked if a.timeline]
    return {
        "conversion": f"{100 * len(booked) / started:.0f}% of chats reached installation" if started else "no chats yet",
        "days": f"{statistics.median(days):g} days (median, start of chat to ready-by)" if days else "no orders yet",
        "cost": "measured in the pilot",
        "chases": "measured in the pilot (tracker replaces the status call)",
        "churn": "measured 6 months after go-live",
    }


def view(apps, booked_on, ready_by) -> list[dict]:
    base, now = baseline(), app_so_far(apps, booked_on, ready_by)
    return [{"id": k, **v, "before": base[k], "app": now[k]} for k, v in TARGETS.items()]

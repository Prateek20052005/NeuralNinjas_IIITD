"""When the app should bring in a person, and what that person is told.

The app sells simple, high-volume plans on its own. A specialist from the business team calls when:
  leased_line - the plan has a dedicated leased line (needs a site survey before installation)
  factory     - factories (machines, firewall, leased lines) are planned with a specialist
  multi_site  - 5 or more sites, or central management across sites (one network and one bill to design)
  unclear     - the chat could not understand the same question 3 times in a row
  gst_help    - an owner without GST asks for help registering
  price       - the owner wants a lower price than the chat may give (negotiate.py)
The owner can still accept online; the call is an offer, never a block. Staff get a short summary built from the
answers (the chat transcript is never kept), so the owner does not have to repeat anything.
"""
from __future__ import annotations

from .catalogue import load_catalogue

REASONS = ("leased_line", "factory", "multi_site", "unclear", "gst_help", "price")
UNCLEAR_AFTER = 3          # the same question not understood this many times in a row
MANY_SITES = 5
KIND = {"micro": "shop or service", "prof": "office or clinic", "multi": "multi-outlet business", "mfg": "factory"}
CURRENT = {"mobile": "mobile hotspot", "home": "home broadband", "business": "business broadband",
           "leased": "leased line", "none": "no internet", "other": "something else"}


def plan_reasons(profile, items: dict[str, int]) -> list[str]:
    """Why a specialist should plan this order with the owner ([] = the app can handle it alone)."""
    out = []
    if {"P05", "P06"} & set(items):
        out.append("leased_line")
    if profile.segment == "mfg":
        out.append("factory")
    if (profile.sites or 1) >= MANY_SITES or "P10" in items:
        out.append("multi_site")
    return out


def summary(a, quote: dict | None) -> str:
    """One paragraph for the person who calls (English, built from the answers; no ID numbers)."""
    p = a.session.profile
    who = " ".join(x for x in (p.business_type or KIND.get(p.segment or "", "business"),
                               f"in {p.city}" if p.city else "") if x)
    size = f"{p.employees or '?'} people, {p.sites or '?'} site{'s' if (p.sites or 1) > 1 else ''}"
    gst = {"active": "GST active", "inactive": "GST cancelled or suspended", "none": "no GST"}.get(p.gstin_status or "",
                                                                                                    "GST not asked yet")
    parts = [f"{who[:1].upper()}{who[1:]}: {size}, {gst}."]
    if p.current_tools:
        parts.append(f"Uses {CURRENT.get(p.current_tools, p.current_tools)} today.")
    if a.current_spend:
        parts.append(f"Pays about Rs {a.current_spend:,} a month today.")
    wants = [k.replace("_", " ") for k in sorted(p.needs_answered) if getattr(p.needs, k, None) is True]
    said_no = [k.replace("_", " ") for k in sorted(p.needs_answered) if getattr(p.needs, k, None) is False]
    if wants:
        parts.append(f"Wants: {', '.join(wants)}.")
    if said_no:
        parts.append(f"Said no to: {', '.join(said_no)}.")
    if p.needs.machines or p.needs.vehicles:
        parts.append(f"Machines: {p.needs.machines}, vehicles: {p.needs.vehicles}.")
    if quote:
        cat = load_catalogue()
        lines = ", ".join(f"{cat[l['product_id']].name}{' x' + str(l['quantity']) if l['quantity'] > 1 else ''}"
                          for l in quote["lines"])
        parts.append(f"Plan shown: {lines}; Rs {quote['monthly_with_gst']:,}/month incl. GST, "
                     f"{quote['contract_months']}-month contract.")
    if a.price_asks:
        parts.append(f"Asked for a lower price {a.price_asks} time{'s' if a.price_asks > 1 else ''}"
                     f"{f', offered {a.discount_pct:g}% off' if a.discount_pct else ''}.")
    return " ".join(parts)

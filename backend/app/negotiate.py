"""Owner asks for a lower price: the chatbot may take up to max_discount_pct off the monthly price, in two steps,
then hands the owner to a salesperson. Numbers live in pricing_settings.json so the business team can change them.

The discount is a share of the monthly price before GST, and it never takes the plan below the catalogue minimum
(the sum of each product's lowest catalogue price), which no past deal ever went below.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

SETTINGS_FILE = Path(__file__).with_name("pricing_settings.json")


@lru_cache(maxsize=1)
def settings() -> dict:
    s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    first, top, hours = float(s["first_offer_pct"]), float(s["max_discount_pct"]), int(s["sales_callback_hours"])
    if not (0 <= first <= top <= 50 and hours > 0):
        raise ValueError("pricing_settings.json: need 0 <= first_offer_pct <= max_discount_pct <= 50, hours > 0")
    return {"first_offer_pct": first, "max_discount_pct": top, "sales_callback_hours": hours}


def room_pct(list_total: int, floor_total: int) -> float:
    """How far (in %) the plan can come down before it hits the catalogue minimum."""
    return 100 * (list_total - floor_total) / list_total if list_total > 0 else 0.0


def next_offer(asks: int, room: float, current: float) -> float | None:
    """The discount % to offer on the owner's n-th ask, or None: time for a salesperson."""
    s = settings()
    steps = [s["first_offer_pct"], s["max_discount_pct"]]
    if asks > len(steps):
        return None
    offer = round(min(steps[asks - 1], room), 1)
    return offer if offer > current + 0.05 else None


def is_last_offer(asks: int, room: float, current: float) -> bool:
    """True when asking again would go to a salesperson (so the message can say 'this is my best price')."""
    return next_offer(asks + 1, room, current) is None


def clean_phone(raw: str) -> str | None:
    """Indian mobile number as 10 digits: '+91 98765-43210', '०९८७६५४३२१०' -> '9876543210'. None if not valid."""
    s = re.sub(r"[\s()-]", "", str(raw or "").translate(str.maketrans("०१२३४५६७८९", "0123456789")))
    s = re.sub(r"^(\+?91|0)(?=\d{10}$)", "", s)
    return s if re.fullmatch(r"[6-9]\d{9}", s) else None


def rupees(n: int) -> str:
    """Indian digit grouping, like the app's screens: 123456 -> '1,23,456'."""
    head, tail = str(int(n))[:-3], str(int(n))[-3:]
    while len(head) > 2:
        tail, head = f"{head[-2:]},{tail}", head[:-2]
    return f"{head},{tail}" if head else tail

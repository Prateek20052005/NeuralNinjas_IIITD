"""Owner asks for a lower price in the chat, after seeing the plan. The first request gets no discount: the owner is
shown the honest ways to pay less (Basic plan, a longer contract). If they insist, the chatbot may take
first_offer_pct and then max_discount_pct off the monthly price; after that it hands the owner to a salesperson.
Numbers live in pricing_settings.json so the business team can change them.

The discount is a share of the monthly price before GST, and it never takes the plan below the catalogue minimum
(the sum of each product's lowest catalogue price), which no past deal ever went below.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .i18n import ascii_digits

SETTINGS_FILE = Path(__file__).with_name("pricing_settings.json")


@lru_cache(maxsize=1)
def settings() -> dict:
    s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    first, top, hours = float(s["first_offer_pct"]), float(s["max_discount_pct"]), int(s["sales_callback_hours"])
    refusals = int(s.get("polite_refusals", 1))
    if not (0 <= first <= top <= 50 and hours > 0 and 0 <= refusals <= 3):
        raise ValueError("pricing_settings.json: need 0 <= first_offer_pct <= max_discount_pct <= 50, hours > 0, "
                         "0 <= polite_refusals <= 3")
    pay_ahead = {int(k): float(v) for k, v in s.get("pay_ahead_saving_pct", {}).items() if not k.startswith("_")}
    w = s["welcome"]
    welcome = {"large_order_from": int(w["large_order_from"]), "very_large_order_from": int(w["very_large_order_from"]),
               "setup_off_pct": {k: float(w["setup_off_pct"][k]) for k in ("small", "large", "very_large")},
               "first_months": int(w["first_months"]), "first_months_pct": float(w["first_months_pct"])}
    if not (set(pay_ahead) <= {3, 6, 12} and all(0 <= v <= 20 for v in pay_ahead.values())
            and 0 < welcome["large_order_from"] <= welcome["very_large_order_from"]
            and all(0 <= v <= 100 for v in welcome["setup_off_pct"].values())
            and 1 <= welcome["first_months"] <= 12 and 0 <= welcome["first_months_pct"] <= 50):
        raise ValueError("pricing_settings.json: pay_ahead_saving_pct must be for 3/6/12 months (0-20%), welcome "
                         "thresholds increasing, setup_off_pct 0-100, first_months 1-12, first_months_pct 0-50")
    return {"first_offer_pct": first, "max_discount_pct": top, "sales_callback_hours": hours,
            "polite_refusals": refusals, "pay_ahead_saving_pct": pay_ahead, "welcome": welcome}


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


def negotiation_step(asks: int, room: float, current: float) -> tuple[str, float | None]:
    """What to do on the owner's n-th request for a lower price:
    ("pushback", None)  no discount yet: show the cheaper plan and longer contracts
    ("offer", pct)      a first discount; ("final", pct) the best the chatbot may give
    ("handoff", None)   nothing more to give: offer a salesperson's call"""
    refusals = settings()["polite_refusals"]
    if asks <= refusals:
        return "pushback", None
    offer = next_offer(asks - refusals, room, current)
    if offer is None:
        return "handoff", None
    return ("final" if is_last_offer(asks - refusals, room, offer) else "offer"), offer


# "Can you give a discount?", "too expensive", "thoda kam karo" in all 7 languages. Latin words match at a word start;
# Indian-script words anywhere (they take endings). Short or ambiguous words ("kam" alone) are left to the AI.
PRICE_WORDS = [
    # English / Hinglish
    "discount", "cheaper", "lower price", "lower the price", "less price", "reduce", "too expensive", "expensive",
    "costly", "too much", "best price", "better price", "better deal", "negotiat", "afford", "kam karo", "kam kar",
    "kam ho", "thoda kam", "price kam", "rate kam", "daam kam", "sasta", "saste", "mehenga", "mehnga", "mahanga",
    "chhoot", "chhut", "concession",
    # Hindi / Marathi
    "छूट", "डिस्काउंट", "सस्ता", "सस्ते", "महंगा", "महँगा", "कम कर", "कम करो", "कम हो", "कीमत कम", "दाम कम",
    "सवलत", "स्वस्त", "महाग", "कमी करा", "किंमत कमी",
    # Gujarati
    "ડિસ્કાઉન્ટ", "છૂટ", "સસ્તું", "સસ્તા", "મોંઘું", "મોંઘા", "ઓછું કરો", "ઓછી કિંમત", "ભાવ ઓછો",
    # Tamil
    "தள்ளுபடி", "டிஸ்கவுண்ட்", "விலை குறை", "விலையைக் குறை", "மலிவு", "அதிக விலை", "குறைச்சு", "கம்மி",
    # Telugu
    "డిస్కౌంట్", "తగ్గింపు", "తక్కువ ధర", "ధర తగ్గించ", "ఖరీదు", "చౌక", "తగ్గించండి",
    # Kannada
    "ರಿಯಾಯಿತಿ", "ಡಿಸ್ಕೌಂಟ್", "ಕಡಿಮೆ ಬೆಲೆ", "ಬೆಲೆ ಕಡಿಮೆ", "ದುಬಾರಿ", "ಅಗ್ಗ", "ಕಡಿಮೆ ಮಾಡಿ",
]


def wants_lower_price(text: str) -> bool:
    s = f" {str(text).lower()} "
    return any((w in s) if re.search(r"[^\x00-\x7f]", w) else re.search(rf"(?<![a-z]){re.escape(w)}", s)
               for w in PRICE_WORDS)


def clean_phone(raw: str) -> str | None:
    """Indian mobile number as 10 digits: '+91 98765-43210', '०९८७६५४३२१०', '೯೮೭...' -> '9876543210'. None if not valid."""
    s = re.sub(r"[\s()-]", "", ascii_digits(raw or ""))
    s = re.sub(r"^(\+?91|0)(?=\d{10}$)", "", s)
    return s if re.fullmatch(r"[6-9]\d{9}", s) else None


def rupees(n: int) -> str:
    """Indian digit grouping, like the app's screens: 123456 -> '1,23,456'."""
    head, tail = str(int(n))[:-3], str(int(n))[-3:]
    while len(head) > 2:
        tail, head = f"{head[-2:]},{tail}", head[:-2]
    return f"{head},{tail}" if head else tail

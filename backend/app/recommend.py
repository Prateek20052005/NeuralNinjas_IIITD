"""Rule-based bundle recommender.

Input: what we know about the business (Business) and what the owner told us they need (Needs).
Output: a bundle that always passes the catalogue rules, with a plain-language reason per product,
plus suggested add-ons the owner can switch on.

Defaults per segment come from what activated customers in smb_leads.csv actually bought
(products in >40% of a segment's bundles are core, 15-40% are suggested add-ons).
The AI advisor only fills in Business/Needs from the conversation and rephrases the reasons;
it never picks products itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .catalogue import Business, check_bundle, check_product, load_catalogue
from .bundles import SHOW_FROM_PCT, rank_extras
from .similar import neighbours, quantity as similar_quantity
from .quote import Quote, build_quote


@dataclass
class Needs:
    """True = owner wants it, False = owner said no, None = not discussed (segment default applies)."""
    internet: bool | None = None          # False -> owner wants mobile lines only, no internet connection
    fibre_available: bool | None = None   # False -> use 5G AirFiber
    billing_pos: bool | None = None       # GST billing / UPI & card counter
    whatsapp: bool | None = None          # reach customers on WhatsApp
    sms: bool | None = None               # bulk SMS alerts / promotions
    cctv: bool | None = None
    guest_wifi: bool | None = None
    website: bool | None = None
    cloud_email: bool | None = None
    backup: bool | None = None
    security: bool | None = None          # antivirus / ransomware protection
    firewall: bool | None = None
    phone_system: bool | None = None      # IVR / business phone lines
    toll_free: bool | None = None
    failover: bool | None = None          # can't afford the internet going down
    central_management: bool | None = None
    static_ip: bool | None = None
    mobile_lines: int | None = None
    cameras: int | None = None
    machines: int = 0                     # machines to monitor (IoT)
    vehicles: int = 0                     # vehicles to track


@dataclass
class Pick:
    product_id: str
    quantity: int
    reason: str
    popularity: dict | None = None        # extras: how often similar businesses took it (bundles.py)


@dataclass
class Recommendation:
    core: list[Pick]
    addons: list[Pick]                    # suggested, switched off by default
    notes: list[str] = field(default_factory=list)  # swaps and things we could not offer, in plain English
    note_items: list[dict] = field(default_factory=list)  # same notes, structured for translation
    quote: Quote | None = None
    essential: set[str] = field(default_factory=set)      # internet, mobile lines and what the owner asked for
    similar: int = 0                                        # how many similar past customers shaped quantities and extras

    def items(self) -> dict[str, int]:
        return {p.product_id: p.quantity for p in self.core}

    def tiers(self) -> dict[str, dict[str, int]]:
        """Basic = only the essentials; Recommended = our suggestion; Full = with every suggested extra.
        Same prices in every tier: only the products change."""
        return {"basic": {p.product_id: p.quantity for p in self.core if p.product_id in self.essential},
                "recommended": self.items(),
                "full": {**self.items(), **{p.product_id: p.quantity for p in self.addons}}}


# Need flag -> product. Quantity is worked out in _quantity().
NEED_PRODUCT = {
    "billing_pos": "P19", "whatsapp": "P15", "sms": "P14", "cctv": "P23", "guest_wifi": "P22",
    "website": "P18", "cloud_email": "P16", "backup": "P17", "security": "P20", "firewall": "P21",
    "phone_system": "P12", "toll_free": "P13", "failover": "P09", "central_management": "P10",
    "static_ip": "P11",
}

# What each segment usually gets when the owner hasn't said yes or no.
SEGMENT_DEFAULTS = {
    "micro": {"core": [], "addons": ["billing_pos", "guest_wifi", "cctv", "whatsapp", "website"]},
    "prof": {"core": ["cloud_email", "security"], "addons": ["backup", "failover", "phone_system", "static_ip", "sms"]},
    "multi": {"core": ["failover", "billing_pos"],
              "addons": ["central_management", "cctv", "toll_free", "whatsapp", "guest_wifi"]},
    "mfg": {"core": ["cloud_email"], "addons": ["security", "firewall", "static_ip", "cctv"]},
}

# If a product can't be sold to this business, try these instead (in order).
FALLBACKS = {
    "P06": ["P05", "P03", "P02"],
    "P05": ["P03", "P02"],
    "P03": ["P02", "P01"],
    "P02": ["P01"],
    "P01": ["P04"],
    "P21": ["P20"],
}

REASONS = {
    "P01": "Fast unlimited fibre so UPI, card payments and billing never stop",
    "P02": "300 Mbps fibre with room for {employees} people working online at once",
    "P03": "1 Gbps fibre with priority support for a busy office",
    "P04": "5G wireless internet that works where fibre can't reach, set up in 2 days",
    "P05": "Dedicated 20 Mbps line with a 99.5% uptime promise, so production never waits on the internet",
    "P06": "Dedicated 100 Mbps line with a 99.9% uptime promise for a large unit",
    "P07": "Business mobile lines with 50 GB data and unlimited calls",
    "P08": "Business mobile lines with 150 GB data, roaming and priority care for staff on the move",
    "P09": "Backup 4G/5G router that switches on by itself if the main internet goes down",
    "P10": "Manage the internet at all {sites} sites from one place, with one bill",
    "P11": "Fixed internet address for CCTV, servers or remote access",
    "P12": "Business phone lines with a welcome menu (IVR) and call recording",
    "P13": "A 1800 toll-free number customers can call for free",
    "P14": "10,000 SMS a month for reminders, alerts and offers",
    "P15": "Verified WhatsApp Business channel with your catalogue",
    "P16": "Email on your own business name plus documents and video meetings",
    "P17": "Automatic 1 TB backup so client files are never lost",
    "P18": "Your own website and domain, easy to build yourself",
    "P19": "GST-ready billing with UPI and card payments on a tablet",
    "P20": "Antivirus and ransomware protection for computers and phones",
    "P21": "Managed firewall watched by Accel's security team",
    "P22": "Secure Wi-Fi with a separate network for customers",
    "P23": "HD cameras with 30 days of cloud recording, viewable on your phone",
    "P24": "Sensors that track machine uptime and power use",
    "P25": "GPS trackers with a live map of your vehicles",
}


def _connectivity(biz: Business, needs: Needs) -> str:
    if needs.fibre_available is False:
        return "P04"
    if biz.segment == "mfg":
        if biz.employees >= 100:
            return "P06"
        if biz.employees >= 25:
            return "P05"
        return "P03"
    if biz.segment == "multi":
        return "P02" if biz.employees / max(biz.sites, 1) >= 8 else "P01"
    if biz.segment == "prof":
        if biz.employees >= 20:
            return "P03"
        return "P02" if biz.employees >= 5 else "P01"
    return "P01"


def _quantity(pid: str, biz: Business, needs: Needs, near: list | None = None) -> int:
    """The owner's own answer first, then what similar businesses bought for their size (similar.py), then a rule."""
    e, s = biz.employees, biz.sites
    per_site = {"P01", "P02", "P03", "P04", "P05", "P06", "P09", "P10", "P19", "P21", "P22"}
    if pid in per_site:
        return s
    if pid in ("P07", "P08") and needs.mobile_lines:
        return needs.mobile_lines
    if pid == "P23" and needs.cameras:
        return needs.cameras
    if near and (q := similar_quantity(near, pid, biz)):
        return q
    if pid in ("P07", "P08"):
        return min(2, e) if biz.segment == "micro" else min(max(1, math.ceil(e / 8)), 6)
    if pid == "P16":  # desk staff who need email
        return min(e, 20) if biz.segment != "mfg" else min(max(5, e // 10), 15)
    if pid == "P20":
        return min(e, 10) if biz.segment != "mfg" else min(max(4, e // 12), 12)
    if pid == "P23":
        return 1 if biz.segment == "micro" else 2 * s
    if pid == "P12":
        return min(max(2, math.ceil(e / 5)), 4)
    if pid == "P24":
        return needs.machines
    if pid == "P25":
        return needs.vehicles
    return 1


def _reason(pid: str, biz: Business) -> str:
    return REASONS[pid].format(employees=biz.employees, sites=biz.sites)


def _place(pid: str, biz: Business, notes: list[str], items: list[dict]) -> str | None:
    """Return pid, or the best allowed substitute, or None (with a note saying why)."""
    cat = load_catalogue()
    check = check_product(pid, biz)
    if check.ok:
        return pid
    code, params = check.codes[0]
    for alt in FALLBACKS.get(pid, []):
        if check_product(alt, biz).ok:
            notes.append(f"{check.reasons[0]}, so we suggested {cat[alt].name} instead.")
            items.append({"type": "swap", "product": pid, "alt": alt, "code": code, "params": params})
            return alt
    notes.append(f"{check.reasons[0]}, so it is not included.")
    items.append({"type": "drop", "product": pid, "code": code, "params": params})
    return None


def recommend(biz: Business, needs: Needs | None = None, order_date=None) -> Recommendation:
    needs = needs or Needs()
    cat = load_catalogue()
    notes: list[str] = []
    note_items: list[dict] = []
    core: dict[str, Pick] = {}
    addons: dict[str, Pick] = {}
    essential: set[str] = set()
    near = neighbours(biz) if biz.segment else []   # businesses like yours (similar.py)

    def add(pid, bucket, must=False):
        placed = _place(pid, biz, notes, note_items)
        needs_one_of = cat[placed].requires_one_of if placed else frozenset()
        if needs_one_of and not needs_one_of & set(core):
            names = " or ".join(cat[n].name for n in sorted(needs_one_of))
            notes.append(f"{cat[placed].name} works only with {names}, so it is not included.")
            note_items.append({"type": "drop", "product": placed, "code": "needs_one_of",
                               "params": {"needs": sorted(needs_one_of)}})
            return
        if placed and placed not in core and placed not in addons:
            qty = _quantity(placed, biz, needs, near)
            if qty > 0:
                bucket[placed] = Pick(placed, qty, _reason(placed, biz))
                if must:
                    essential.add(placed)

    # Mobile-only owners get mobile lines plus what they asked for. Segment defaults become optional extras,
    # and extras that need an internet line are left out quietly (they did not ask for them).
    mobile_only = needs.internet is False

    def needs_line(pid):
        return mobile_only and bool(cat[pid].requires_one_of)

    # 1. Internet line (everything else hangs off it) and mobile lines
    if not mobile_only:
        add(_connectivity(biz, needs), core, must=True)
    # shops and offices: the 299-399 line (offices split ~50/50 in past sales, and owners asked for the cheaper one);
    # chains and factories: the 599-799 line with roaming, which every one of them bought
    add("P07" if biz.segment in ("micro", "prof") else "P08", core, must=True)

    # 2. What the owner asked for, then segment defaults for things not discussed
    defaults = SEGMENT_DEFAULTS[biz.segment]
    core_defaults = [] if mobile_only else defaults["core"]
    addon_defaults = defaults["core"] + defaults["addons"] if mobile_only else defaults["addons"]
    for flag, pid in NEED_PRODUCT.items():
        wanted = getattr(needs, flag)
        if wanted is True or (wanted is None and flag in core_defaults):
            add(pid, core, must=wanted is True)
    def allowed(pid):   # an extra the owner never asked about is left out quietly if they can't have it
        return any(check_product(x, biz).ok for x in [pid, *FALLBACKS.get(pid, [])])

    for flag in addon_defaults:
        if getattr(needs, flag) is None and not needs_line(NEED_PRODUCT[flag]) and allowed(NEED_PRODUCT[flag]):
            add(NEED_PRODUCT[flag], addons)
    if needs.machines:
        add("P24", core, must=True)
    if needs.vehicles:
        add("P25", core, must=True)

    # 3. Safety net: drop anything whose companion product is missing (should not happen, but never quote it)
    for pid, check in check_bundle({**{p: 1 for p in core}}, biz).items():
        if not check.ok:
            notes.append(f"{check.reasons[0]}, so it is not included.")
            note_items.append({"type": "drop", "product": pid, "code": check.codes[0][0], "params": check.codes[0][1]})
            core.pop(pid)
    # 4. Extras in the order similar businesses took them, each with that share (bundles.py: rules per kind of business)
    ranked = rank_extras(biz.segment, set(core), list(addons), near)
    extras = []
    for pid, seen in ranked:
        pick = addons[pid]
        pick.popularity = seen if seen and seen["pct"] >= SHOW_FROM_PCT else None
        extras.append(pick)
    rec = Recommendation(list(core.values()), extras, notes, note_items, essential=essential, similar=len(near))
    rec.quote = build_quote(rec.items(), biz, order_date)
    return rec

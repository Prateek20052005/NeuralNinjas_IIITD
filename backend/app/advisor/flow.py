"""Conversation state and the fixed question order shared by the scripted and AI advisors.

Both modes fill the same Profile and ask about the same next missing slot, so the AI never changes what
is asked or decided; questions are always worded from the i18n files. Order: GSTIN first (it pre-fills
name and city), then business kind, city, staff, sites, what internet they need (fibre, 5G wireless, not sure,
or mobile lines only), and 2-3 needs questions for that kind of business.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..catalogue import Business, load_catalogue
from ..customers import is_existing_customer
from ..i18n import t
from ..kyc.lookups import find_gstin_in_text, lookup_gstin, mask
from ..recommend import NEED_PRODUCT, Needs, Recommendation, recommend
from ..reference import canonical_city, city_tier, find_city
from .parse import internet_choice, kind_of_business, number, yes_no

NEED_QUESTIONS = {
    "micro": ["billing_pos", "whatsapp", "cctv"],
    "prof": ["phone_system", "backup", "failover"],
    "multi": ["central_management", "cctv", "toll_free"],
    "mfg": ["machines", "vehicles", "firewall"],
}
COUNT_NEEDS = {"machines", "vehicles"}  # asked as numbers, not yes/no
INTERNET_OPTIONS = ("fibre", "wireless", "unsure", "mobile")
CITY_BUTTONS = ["Mumbai", "Delhi", "Bengaluru", "Pune", "Hyderabad", "Chennai", "Kolkata", "Ahmedabad", "Jaipur",
                "Lucknow", "Nagpur", "Surat"]


@dataclass
class Profile:
    language: str = "en"
    gstin: str | None = None
    gstin_status: str | None = None       # 'active' | 'inactive' | 'none'  (None = not asked yet)
    gst_confirmed: bool | None = None     # owner said the registry name/city is their business
    city_from_gst: bool = False
    stated_city: str | None = None        # city the owner typed while a GST city was filled in
    business_name: str | None = None
    segment: str | None = None
    business_type: str | None = None
    city: str | None = None
    city_tier: int | None = None
    employees: int | None = None
    sites: int | None = None
    needs: Needs = field(default_factory=Needs)
    needs_answered: set[str] = field(default_factory=set)
    city_other_asked: bool = False
    existing_customer: bool | None = None   # already with Accel? (GSTIN: our records; no GSTIN: we ask)

    def safe_view(self) -> dict:
        """Profile as shown to the AI and written to logs: identifiers masked."""
        return {"language": self.language, "gstin": mask(self.gstin), "gst_status": self.gstin_status,
                "business_name": self.business_name, "kind": self.segment, "business_type": self.business_type,
                "city": self.city, "employees": self.employees, "sites": self.sites,
                "needs": {k: getattr(self.needs, k) for k in self.needs_answered},
                "existing_customer": self.existing_customer}

    def ai_view(self) -> dict:
        """What the chat AI may see: no GST number and no business name (it needs neither to suggest a plan)."""
        return {k: v for k, v in self.safe_view().items() if k not in ("gstin", "business_name")}


def _needs_internet_line(p: Profile, need: str) -> bool:
    """Mobile-only owners are not asked about products that only work with an internet line."""
    pid = NEED_PRODUCT.get(need)
    return p.needs.internet is False and bool(pid and load_catalogue()[pid].requires_one_of)


def next_slot(p: Profile) -> str | None:
    if p.gstin_status is None:
        return "gstin"
    if p.gstin and p.gst_confirmed is None:
        return "gst_confirm"
    if p.gstin_status == "none" and p.existing_customer is None:   # no GSTIN to check our records with
        return "existing"
    if p.segment is None:
        return "segment"
    if p.city is None:
        return "city"
    if p.employees is None:
        return "employees"
    if p.sites is None:
        return "sites"
    if "internet" not in p.needs_answered and p.needs.internet is None and p.needs.fibre_available is None:
        return "internet"
    for need in NEED_QUESTIONS[p.segment]:
        if need not in p.needs_answered and not _needs_internet_line(p, need):
            return f"need:{need}"
    return None


def progress(p: Profile, slot: str) -> dict:
    """Where this question sits in the chat, for the "3 of 8" bar. The total can change as answers come in
    (a GSTIN adds the "is this your business?" step; the kind of business decides the need questions)."""
    plan = (["gstin"] + (["gst_confirm"] if p.gstin else []) + (["existing"] if p.gstin_status == "none" else [])
            + ["segment", "city", "employees", "sites", "internet"])
    plan += [f"need:{n}" for n in NEED_QUESTIONS.get(p.segment) or NEED_QUESTIONS["micro"]
             if not _needs_internet_line(p, n)]
    return {"step": plan.index(slot) + 1 if slot in plan else len(plan), "steps": len(plan)}


def question(p: Profile, slot: str) -> dict:
    """The question for a slot, in the owner's language, with tap-to-answer options and its place in the chat."""
    return {**_ask(p, slot), **progress(p, slot)}


def _ask(p: Profile, slot: str) -> dict:
    lang = p.language
    if slot == "gstin":
        return {"slot": slot, "text": t(lang, "q.gstin"), "input": "text",
                "options": [{"value": "none", "label": t(lang, "opt.no_gst")}]}
    if slot == "gst_confirm":
        return {"slot": slot, "text": t(lang, "q.gst_confirm", name=p.business_name, city=p.city or ""),
                "input": "choice",
                "options": [{"value": "yes", "label": t(lang, "opt.yes")}, {"value": "no", "label": t(lang, "opt.no")}]}
    if slot == "existing":
        return {"slot": slot, "text": t(lang, "q.existing_customer"), "input": "choice",
                "options": [{"value": "no", "label": t(lang, "opt.existing.no")},
                            {"value": "yes", "label": t(lang, "opt.existing.yes")}]}
    if slot == "segment":
        return {"slot": slot, "text": t(lang, "q.segment"), "input": "choice",
                "options": [{"value": s, "label": t(lang, f"opt.segment.{s}")} for s in ("micro", "prof", "multi", "mfg")]}
    if slot == "city":
        if p.city_other_asked:
            return {"slot": slot, "text": t(lang, "q.city_other"), "input": "text", "options": []}
        return {"slot": slot, "text": t(lang, "q.city"), "input": "choice",
                "options": [{"value": c, "label": c} for c in CITY_BUTTONS]
                + [{"value": "other", "label": t(lang, "opt.other_city")}]}
    if slot == "employees":
        return {"slot": slot, "text": t(lang, "q.employees"), "input": "number",
                "options": [{"value": v, "label": v} for v in ("1", "3", "5", "10", "20", "50")]}
    if slot == "sites":
        return {"slot": slot, "text": t(lang, "q.sites"), "input": "number",
                "options": [{"value": v, "label": v} for v in ("1", "2", "3", "5", "10")]}
    if slot == "internet":
        return {"slot": slot, "text": t(lang, "q.internet"), "input": "choice",
                "options": [{"value": o, "label": t(lang, f"opt.internet.{o}")} for o in INTERNET_OPTIONS]}
    need = slot.split(":", 1)[1]
    if need in COUNT_NEEDS:
        return {"slot": slot, "text": t(lang, f"q.{need}"), "input": "number",
                "options": [{"value": v, "label": v} for v in ("0", "2", "5", "10")]}
    return {"slot": slot, "text": t(lang, f"q.need.{need}"), "input": "choice",
            "options": [{"value": "yes", "label": t(lang, "opt.yes")}, {"value": "no", "label": t(lang, "opt.no")}]}


def _to_int(value) -> int | None:
    return number(value)


def _city_from_address(address: str) -> str | None:
    """'Shop/Unit 1, Tech Park Road, Visakhapatnam, Andhra Pradesh - 118383' -> 'Visakhapatnam'."""
    parts = [x.strip() for x in address.split(",")]
    return parts[-2] if len(parts) >= 3 else None


def set_city(p: Profile, name: str) -> None:
    p.city = canonical_city(name)
    p.city_tier = city_tier(p.city)  # unknown towns count as tier 2


def apply_answer(p: Profile, slot: str, value) -> list[str]:
    """Store an answer. Returns messages to show the owner (already translated)."""
    lang, msgs = p.language, []
    value = "" if value is None else str(value).strip()

    if slot == "gstin":
        found = find_gstin_in_text(value)
        skip = {"skip", "later", "baad", "बाद", "नंतर", "પછી", "pachi", "பிறகு", "அப்புறம்", "apparam",
                "తర్వాత", "తరువాత", "taruvata", "ನಂತರ"} & set(value.lower().replace(",", " ").split())
        if not found and (value.lower() in ("none", "") or yes_no(value) is False or skip):
            p.gstin_status = "none"
            return [t(lang, "msg.no_gst")]
        r = lookup_gstin(found or value)
        if not r.format_ok:
            return [t(lang, "msg.gst_invalid")]
        if not r.found:
            return [t(lang, "msg.gst_notfound")]
        p.gstin, p.gstin_status, p.business_name = r.gstin, r.business_status, r.trade_name
        p.existing_customer = is_existing_customer(r.gstin)   # our records decide; no need to ask
        city = _city_from_address(r.address or "")
        if city and p.city is None:
            set_city(p, city)
            p.city_from_gst = True
        if r.active:
            msgs.append(t(lang, "msg.gst_found", name=r.trade_name, city=p.city or r.state))
        else:
            msgs.append(t(lang, "msg.gst_inactive", name=r.trade_name, status=t(lang, f"status.{r.status}")))
        return msgs

    if slot == "gst_confirm":
        yn = yes_no(value)
        if yn is None:
            return [t(lang, "msg.yes_no_hint"), question(p, slot)["text"]]
        if yn:
            p.gst_confirmed = True
            return msgs
        # Not their business: forget everything that came from this GST number and ask again
        if p.city_from_gst:
            p.city, p.city_tier, p.city_from_gst = None, None, False
            if p.stated_city:
                set_city(p, p.stated_city)
        p.gstin = p.gstin_status = p.business_name = p.gst_confirmed = p.existing_customer = None
        return [t(lang, "msg.gst_rejected")]

    if slot == "existing":
        yn = yes_no(value)
        if yn is None:
            return [t(lang, "msg.yes_no_hint"), question(p, slot)["text"]]
        p.existing_customer = yn
        return [t(lang, "msg.existing.yes" if yn else "msg.existing.no")]

    if slot == "segment":
        if value in ("micro", "prof", "multi", "mfg"):
            p.segment = value
        elif kind := kind_of_business(value):   # typed instead of tapped: "kirana store", "कापड कारखाना"
            p.segment = kind
            p.business_type = p.business_type or value[:60]
        else:
            return [t(lang, "msg.pick_option"), question(p, slot)["text"]]
        return msgs

    if slot == "city":
        if value == "other":
            p.city_other_asked = True
        elif city := find_city(value):
            set_city(p, city)
        elif value:
            p.city_other_asked = True   # a long sentence with no town we know: ask for just the name
        return msgs

    if slot in ("employees", "sites"):
        n = _to_int(value)
        if n is None or n < 1:
            return [t(lang, "msg.invalid_number")]
        setattr(p, slot, min(n, 1000))
        if slot == "sites" and n >= 3 and p.segment in ("micro", "prof"):
            p.segment = "multi"
            msgs.append(t(lang, "msg.became_multi", sites=n))
        return msgs

    if slot == "internet":
        choice = internet_choice(value)
        if choice is None:
            return [t(lang, "msg.pick_option"), question(p, slot)["text"]]
        p.needs.internet = choice != "mobile"
        if choice in ("fibre", "wireless"):
            p.needs.fibre_available = choice == "fibre"
        if choice != "fibre":
            msgs.append(t(lang, f"msg.internet.{choice}"))
        p.needs_answered.add("internet")
        return msgs

    need = slot.split(":", 1)[1]
    if need in COUNT_NEEDS:
        n = _to_int(value)
        if n is None:
            return [t(lang, "msg.invalid_number")]
        setattr(p.needs, need, min(n, 200))
    else:
        yn = yes_no(value)
        if yn is None:  # unclear answer: say so and ask the same question again
            return [t(lang, "msg.yes_no_hint"), question(p, slot)["text"]]
        setattr(p.needs, need, yn)
    p.needs_answered.add(need)
    return msgs


def to_business(p: Profile) -> Business:
    return Business(segment=p.segment, city_tier=p.city_tier or 2, employees=p.employees or 1, sites=p.sites or 1,
                    gstin_status=p.gstin_status or "none", business_type=p.business_type or "", city=p.city or "")


def build_recommendation(p: Profile, order_date=None) -> Recommendation:
    return recommend(to_business(p), p.needs, order_date)


def explain_scripted(p: Profile, rec: Recommendation) -> dict:
    """Template explanation in the owner's language (used when the AI is off or fails)."""
    lang, cat = p.language, load_catalogue()
    biz = to_business(p)

    def name_list(ids):
        return " / ".join(cat[i].name for i in ids)

    def note_text(n):
        rule = t(lang, f"rule.{n['code']}", product=cat[n["product"]].name,
                 needs=name_list(n["params"].get("needs", [])), **{k: v for k, v in n["params"].items() if k != "needs"})
        if n["type"] == "swap":
            return t(lang, "note.swap", rule=rule, alt=cat[n["alt"]].name)
        return t(lang, "note.drop", rule=rule)

    return {
        "headline": t(lang, "msg.ready", segment=t(lang, f"segment.{p.segment}"), city=p.city),
        "reasons": {pick.product_id: t(lang, f"reason.{pick.product_id}", employees=biz.employees, sites=biz.sites)
                    for pick in rec.core + rec.addons},
        "notes": [note_text(n) for n in rec.note_items],
        "price_note": t(lang, "msg.price_note"),
    }

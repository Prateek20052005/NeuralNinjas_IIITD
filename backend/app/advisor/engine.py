"""Advisor session: runs one conversation turn in AI mode or scripted mode.

The AI only (1) pulls facts out of free text and answers questions the owner asks (no small talk, no
promises), and (2) explains the finished bundle in the owner's language. The next question, its order and
its wording always come from flow.py and the i18n files. Facts it extracts are validated here before use; products,
quantities and prices always come from recommend.py and quote.py.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field, replace

from ..catalogue import SEGMENTS, load_catalogue
from ..i18n import AI_LANGUAGE_NAMES as LANG_NAMES
from ..i18n import INDIC_RE, LANGUAGES, script_share, t
from ..kyc.lookups import find_gstin_in_text, redact_ids
from ..quote import Quote
from ..recommend import Recommendation
from .flow import (COUNT_NEEDS, Profile, apply_answer, build_recommendation, explain_scripted,
                   next_slot, question, set_city)
from ..reference import find_city
from .llm import LLM, LLMUnavailable
from .parse import internet_choice, kind_of_business
from .parse import number as _number
from .parse import yes_no as _yes_no

log = logging.getLogger("advisor")
PRICE_TALK = re.compile(r"₹|\brs\.?\s*\d|\brupees?\b|रुपय|रुपए|रुपये|\d+\s*/\s*(month|mo)\b|per month", re.I)
NEED_HINTS = {
    "billing_pos": "GST billing / UPI & card payments", "whatsapp": "reach customers on WhatsApp",
    "sms": "bulk SMS", "cctv": "security cameras", "guest_wifi": "Wi-Fi for customers", "website": "website",
    "cloud_email": "business email", "backup": "file backup", "security": "antivirus", "firewall": "firewall",
    "phone_system": "business phone lines / IVR", "toll_free": "1800 number", "failover": "backup internet",
    "central_management": "manage all sites centrally", "static_ip": "static IP",
}


def _catalogue_brief() -> str:
    # first clause of each description only: keeps each AI turn small (Groq free tier: 8K tokens/minute)
    return "\n".join(f"{p.name}: {p.description.split(',')[0]}" for p in load_catalogue().values())


TURN_PROMPT = """You help a small Indian business owner who is chatting on their phone with Accel Business.
The app asks the questions itself. Your job: understand the owner's latest message.
You get PROFILE (facts already known), JUST_ASKED (the question the owner is replying to) and OWNER SAYS.
Return a JSON object: {{"extract": {{...}}, "say": "..."}}

"extract": facts the owner clearly stated in this message. Leave a key out if unsure.
Never decide anything for the owner: asking about a product ("what does CCTV do?") is not wanting it. A short reply ("yes", "haan", "ho", "no", "nahi", a number) answers JUST_ASKED.
Allowed keys:
  gst_is_theirs: true/false (only when JUST_ASKED is the GST business check; false if they say no,
    "not us", or name a different business)
  no_gstin: true | kind: "micro"|"prof"|"multi"|"mfg" | business_type: short text | city: name in English |
  employees: integer (people incl. owner) | sites: integer (shops/branches/clinics; "just one shop" = 1) | fibre_available: boolean |
  mobile_only: true (owner wants only mobile SIMs, no internet connection) | mobile_lines: integer |
  machines: integer | vehicles: integer | needs: {{flag: true/false}}
kind: micro = one shop or service (kirana, salon, pharmacy, bakery, boutique); prof = office or clinic
(CA, doctor, dentist, lawyer, coaching, agency); multi = chain with several outlets; mfg = factory, workshop, unit.
need flags: {need_flags}

"say": "" unless the owner asked something. If they did, answer only that, ONLY in {language}, at most
2 short sentences, product names in English, saying what the product does (from the CATALOGUE), not that they
will get it: what they can get is checked later (some products need GST, a bigger team or a tier-1 city).
Do NOT ask any question. Never mention prices. Never show field names or codes.

CATALOGUE:
{catalogue}"""

EXPLAIN_PROMPT = """You explain a recommended telecom bundle to a small Indian business owner.
Write ONLY in {language}. Keep product names in English. Simple, warm, specific to their business.
Do NOT mention any price, rupee amount or number of months; the screen shows those.
Return a JSON object:
{{"summary": "2-3 sentences on why this package fits their business",
  "reasons": {{"<product id>": "one short sentence for each product id given"}},
  "notes": ["one sentence for each note given, same order"]}}"""


@dataclass
class Session:
    profile: Profile = field(default_factory=Profile)
    recommendation: Recommendation | None = None
    explanation: dict | None = None
    ai_used: bool = False
    fallbacks: list[str] = field(default_factory=list)


class Advisor:
    def __init__(self, llm: LLM | None = None, order_date=None):
        self.llm = llm or LLM()
        self.order_date = order_date

    # ---------- public ----------
    def start(self, language: str = "en") -> tuple[Session, dict]:
        s = Session(Profile(language=language if language in LANGUAGES else "en"))
        lang = s.profile.language
        q = question(s.profile, next_slot(s.profile))
        notice = [t(lang, "msg.ai_notice")] if self.llm.available else []   # owners are told an AI reads replies
        return s, {"messages": [t(lang, "intro"), *notice, q["text"]], "question": q, "mode": self.mode}

    @property
    def mode(self) -> str:
        return "ai" if self.llm.available else "scripted"

    def handle(self, s: Session, text: str | None = None, slot: str | None = None, value=None) -> dict:
        """One owner turn: either a tapped option (slot + value) or free text."""
        msgs: list[str] = []
        if slot is not None:  # button tap: same in both modes, no AI needed
            if slot == next_slot(s.profile):   # a tap on an old question (double tap, stale screen) changes nothing
                msgs += apply_answer(s.profile, slot, value)
            reply = None
        else:
            asked = next_slot(s.profile)  # the question on the owner's screen, before any prefill
            msgs += self._prefill_ids(s, text or "")
            # a short clear "yes"/"no"/number for the question on screen needs no AI: our parser decides
            use_ai = self.llm.available and not _plain_answer(asked, text or "")
            reply = self._ai_turn(s, text or "", msgs, asked) if use_ai else None
            if reply is None:  # no AI (or it failed): treat the text as the answer to the current question
                current = next_slot(s.profile)
                if current and current == asked:  # a GSTIN just looked up already answered the question on screen
                    msgs += apply_answer(s.profile, current, text)

        nxt = next_slot(s.profile)
        q = question(s.profile, nxt) if nxt else None  # the next question is always ours: fixed order and wording
        if reply and not (q and _same_text(reply, q["text"])):  # AI's answer to the owner's question, never an echo
            msgs.append(reply)
        if q is None:
            return self._finish(s, msgs)
        if not (msgs and msgs[-1] == q["text"]):  # an unclear answer already repeated the question
            msgs.append(q["text"])
        return {"messages": msgs, "question": q, "mode": self.mode, "profile": s.profile.safe_view()}

    # ---------- AI turn ----------
    def _prefill_ids(self, s: Session, text: str) -> list[str]:
        """GSTINs in free text are looked up by code before the AI sees the message."""
        g = find_gstin_in_text(text)
        if g and s.profile.gstin_status is None:
            return apply_answer(s.profile, "gstin", g)
        return []

    def _ai_turn(self, s: Session, text: str, msgs: list[str], asked: str | None) -> str | None:
        """Returns the AI's answer to the owner's question ("" if none), or None if the AI was unavailable."""
        p = s.profile
        system = TURN_PROMPT.format(language=LANG_NAMES[p.language], catalogue=_catalogue_brief(),
                                    need_flags=", ".join(f"{k} ({v})" for k, v in NEED_HINTS.items()))
        answering = asked if asked == next_slot(p) else None  # a fresh GSTIN lookup raises a question not yet shown
        just_asked = question(replace(p, language="en"), answering)["text"] if answering else "nothing"
        # Data minimisation: the AI gets the current message only (no chat history), with ID numbers and the
        # business name removed, plus the answers so far without GST number or business name.
        names = (p.business_name or "",)   # also inside JUST_ASKED: "Is this your business: <name>, <city>?"
        context = (f"PROFILE: {p.ai_view()}\nJUST_ASKED: {redact_ids(just_asked, names)}"
                   f"\nOWNER SAYS: {redact_ids(text, names)}")
        convo = [{"role": "user", "content": context}]
        try:
            out = self.llm.chat_json(system, convo)
        except LLMUnavailable as e:
            s.fallbacks.append(f"turn:{e}")
            return None
        s.ai_used = True
        before = p.safe_view()
        extract = out.get("extract") if isinstance(out.get("extract"), dict) else {}
        if answering == "segment" and kind_of_business(text):
            msgs += apply_answer(p, "segment", text)   # the owner's own words win: the AI once read "दवाई की दुकान" as a clinic
        if answering == "gst_confirm":
            # identity check: a clear yes/no in the owner's own words decides; the AI's reading is only a backup
            yn = _yes_no(text)
            if yn is None and isinstance(extract.get("gst_is_theirs"), bool):
                yn = extract["gst_is_theirs"]
            if yn is not None:
                msgs += apply_answer(p, "gst_confirm", "yes" if yn else "no")
        msgs += self._apply_extract(p, extract, answering)
        # Safety net: a plain yes/no or number the AI failed to record for the question just asked
        if answering and next_slot(p) == answering and len(text.split()) <= 6:
            kind = _answer_kind(answering)
            if kind == "number" and (n := _number(text)) is not None:
                msgs += apply_answer(p, answering, n)
                s.fallbacks.append(f"safety_net:{answering}")
            elif kind == "yes_no" and (yn := _yes_no(text)) is not None:
                msgs += apply_answer(p, answering, "yes" if yn else "no")
                s.fallbacks.append(f"safety_net:{answering}")
            elif answering == "internet" and internet_choice(text):
                msgs += apply_answer(p, answering, text)
                s.fallbacks.append(f"safety_net:{answering}")
            elif answering == "city" and find_city(text, known_only=True):
                msgs += apply_answer(p, answering, text)
                s.fallbacks.append(f"safety_net:{answering}")
        say = out.get("say") if isinstance(out.get("say"), str) else ""
        # questions are ours alone: drop any the AI slipped in, so the owner never gets two at once
        sentences = [x.strip() for x in re.findall(r"[^.!?？।]+[.!?？।]*", say) if x.strip()]
        # prices come only from the quote screen: drop any sentence where the AI states one
        say = " ".join(x for x in sentences if x[-1] not in "?？" and not PRICE_TALK.search(x))
        say = say if len(say.split()) >= 3 and _in_language(say, p.language) else ""  # a stray "ok" is not an answer
        # Nothing understood and nothing to say: let the code reply, so the owner hears why the question repeats
        if answering and answering != "city" and not say and not msgs and p.safe_view() == before:
            msgs += apply_answer(p, answering, text)
            s.fallbacks.append(f"no_progress:{answering}")
        return say

    def _apply_extract(self, p: Profile, ex: dict, answering: str | None = None) -> list[str]:
        """Validate every AI-extracted fact before it touches the profile. Returns messages for the owner."""
        msgs = []
        if ex.get("no_gstin") is True and p.gstin_status is None and answering == "gstin":
            p.gstin_status = "none"
        if ex.get("kind") in SEGMENTS and p.segment is None:
            p.segment = ex["kind"]
        if isinstance(ex.get("business_type"), str) and ex["business_type"].strip():
            p.business_type = ex["business_type"].strip()[:60]
        if isinstance(ex.get("city"), str) and ex["city"].strip():
            if p.city is None:
                set_city(p, ex["city"])
            elif p.city_from_gst and p.gst_confirmed is None:
                p.stated_city = ex["city"].strip()  # kept in case the GST business turns out not to be theirs
        for key in ("employees", "sites"):
            n = _int(ex.get(key))
            if n and 1 <= n <= 1000 and getattr(p, key) is None:
                msgs += apply_answer(p, key, n)
        if isinstance(ex.get("fibre_available"), bool):
            p.needs.fibre_available = ex["fibre_available"]
        if ex.get("mobile_only") is True and p.needs.internet is None and p.needs.fibre_available is None:
            p.needs.internet = False
            p.needs_answered.add("internet")
        if _int(ex.get("mobile_lines")):
            p.needs.mobile_lines = min(_int(ex["mobile_lines"]), 50)
        for key in COUNT_NEEDS:
            n = _int(ex.get(key))
            if n is not None and 0 <= n <= 200:
                setattr(p.needs, key, n)
                p.needs_answered.add(key)
        needs = ex.get("needs") if isinstance(ex.get("needs"), dict) else {}
        needs.update({k: v for k, v in ex.items() if k in NEED_HINTS})  # flags sometimes come at top level
        for flag, val in needs.items():
            val = _yes_no(val) if isinstance(val, str) else val
            if flag in NEED_HINTS and isinstance(val, bool):
                setattr(p.needs, flag, val)
                p.needs_answered.add(flag)
        return msgs

    # ---------- finish: recommendation + explanation ----------
    def _finish(self, s: Session, msgs: list[str]) -> dict:
        p = s.profile
        rec = build_recommendation(p, self.order_date)
        expl = explain_scripted(p, rec)
        if self.llm.available:
            expl = self._ai_explain(s, rec, expl)
        s.recommendation, s.explanation = rec, expl
        msgs.append(expl["headline"])
        return {"messages": msgs, "question": None, "mode": self.mode, "profile": p.safe_view(),
                "recommendation": recommendation_view(rec, expl)}

    def _ai_explain(self, s: Session, rec: Recommendation, fallback: dict) -> dict:
        p, cat = s.profile, load_catalogue()
        payload = {
            "business": {k: v for k, v in p.ai_view().items() if k != "language"},
            "products": {pk.product_id: f"{cat[pk.product_id].name} x{pk.quantity}: {pk.reason}"
                         for pk in rec.core + rec.addons},
            "notes": rec.notes,
        }
        try:
            out = self.llm.chat_json(EXPLAIN_PROMPT.format(language=LANG_NAMES[p.language]),
                                     [{"role": "user", "content": str(payload)}], max_tokens=1500)
        except LLMUnavailable as e:
            s.fallbacks.append(f"explain:{e}")
            return fallback
        s.ai_used = True
        reasons = out.get("reasons") if isinstance(out.get("reasons"), dict) else {}
        notes = out.get("notes") if isinstance(out.get("notes"), list) else []
        merged = dict(fallback)
        # keep the template sentence for any product the AI skipped
        lang = p.language

        def ok(x):
            return isinstance(x, str) and x.strip() and _in_language(x, lang) and not PRICE_TALK.search(x)
        merged["reasons"] = {pid: (reasons.get(pid) if ok(reasons.get(pid)) else text)
                             for pid, text in fallback["reasons"].items()}
        merged["notes"] = [n if ok(n) else f for n, f in zip(notes, fallback["notes"])] \
            if len(notes) == len(fallback["notes"]) else fallback["notes"]
        if ok(out.get("summary")):
            merged["summary"] = out["summary"].strip()
        return merged


def _answer_kind(slot: str | None) -> str | None:
    if slot in ("employees", "sites") or (slot or "")[5:] in COUNT_NEEDS:
        return "number"
    if slot == "gst_confirm" or (slot or "").startswith("need:"):
        return "yes_no"
    return None


def _plain_answer(slot: str | None, text: str) -> bool:
    if len(text.split()) > 4 or "?" in text:
        return False
    if slot == "gstin":   # "none", "GST नाही", "nahi hai": the AI missed these, the code never does
        return bool(find_gstin_in_text(text)) or _yes_no(text) is False or text.strip().lower() in ("none", "skip")
    if slot == "internet":
        return internet_choice(text) is not None
    kind = _answer_kind(slot)
    return (kind == "number" and _number(text) is not None) or (kind == "yes_no" and _yes_no(text) is not None)


def _in_language(text: str, lang: str) -> bool:
    """Indian-language text must be mostly in that language's own script (product names stay English) and not in
    another Indian script (a Hindi reply for a Tamil owner); English must have no Indian script at all."""
    if lang == "en":
        return not INDIC_RE.search(text)
    own, latin = script_share(text, lang)
    other = len(INDIC_RE.findall(text)) - own
    return own > 0 and own >= latin * 0.5 and own > other


def _same_text(a: str, b: str) -> bool:
    a, b = ("".join(c for c in x.lower() if c.isalnum()) for x in (a, b))
    return bool(a) and (a in b or b in a)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def recommendation_view(rec: Recommendation, expl: dict) -> dict:
    q = rec.quote
    return {
        "headline": expl["headline"], "summary": expl.get("summary"), "notes": expl["notes"],
        "price_note": expl["price_note"],
        "core": [{"id": pk.product_id, "quantity": pk.quantity, "reason": expl["reasons"][pk.product_id]}
                 for pk in rec.core],
        "addons": [{"id": pk.product_id, "quantity": pk.quantity, "reason": expl["reasons"][pk.product_id]}
                   for pk in rec.addons],
        "quote": quote_view(q),
    }


def quote_view(q: Quote) -> dict:
    return {**{k: v for k, v in asdict(q).items() if k != "lines"}, "expected_live": q.expected_live.isoformat(),
            "lines": [asdict(line) for line in q.lines]}

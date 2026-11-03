"""HTTP API for the phone web app: advisor chat -> quote with add-on switches -> consent -> KYC -> tracker.

Run: .venv/Scripts/python -m uvicorn backend.app.main:app --reload
All state is per application id (an unguessable token the phone keeps). See store.py for privacy rules.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .advisor.engine import Advisor, quote_view
from .advisor.flow import to_business
from .catalogue import INTERNET_LINES, load_catalogue
from .i18n import LANGUAGES, _strings, t
from .kyc.checks import Issue, KycContext, assess, required_documents
from .kyc.documents import DOC_TYPES, read_document
from .kyc.lookups import clean_id, mask
from .kyc.messages import owner_message, result_view
from .kyc.ocr import NotAnImage
from .negotiate import clean_phone, is_last_offer, next_offer, room_pct, rupees, settings as price_settings
from .quote import build_quote, price_position, toggle, unit_price
from .voice import MAX_AUDIO_BYTES, VOICE_LANGUAGES, Transcriber, VoiceUnavailable
from .store import CONSENT_PURPOSES, Application, Consent, Store, masked_fields

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(levelname)s %(message)s")


class _ShortIds(logging.Filter):
    """The application id is the owner's only key to their data: access logs keep just its first 6 characters."""
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(re.sub(r"(/applications/[\w-]{6})[\w-]+", r"\1~", a) if isinstance(a, str) else a
                                for a in record.args)
        return True


logging.getLogger("uvicorn.access").addFilter(_ShortIds())
TODAY = date.fromisoformat(os.getenv("APP_TODAY") or date.today().isoformat())
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_MESSAGE_CHARS = 500   # a chat reply; longer pastes are cut so one message can't use up the AI budget

app = FastAPI(title="Accel Business - Udyam Digital", version="0.4")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
advisor = Advisor(order_date=TODAY)
transcriber = Transcriber(advisor.llm.client)   # voice answers use the same Groq key as the chat
store = Store()


# ---------- request bodies ----------
class StartBody(BaseModel):
    language: str = "en"


class MessageBody(BaseModel):
    text: str | None = None
    slot: str | None = None      # a tapped option: slot + value
    value: str | int | None = None


class PlanBody(BaseModel):
    tier: str | None = None               # basic / recommended / full
    contract_months: int | None = None
    setup_months: int | None = None       # 1 = pay setup at once, 6 or 12 = spread


class CallbackBody(BaseModel):
    phone: str
    consent: bool                         # "call me about the price of this plan"
    target_monthly: int | None = None     # price that would work for the owner, if they said


class AddonBody(BaseModel):
    product_id: str
    on: bool          # switched on at the suggested quantity


class ConsentBody(BaseModel):
    purposes: list[str]


class UdyamBody(BaseModel):
    number: str


# ---------- helpers ----------
def _app(app_id: str) -> Application:
    a = store.get(app_id)
    if not a:
        raise HTTPException(404, "Application not found or deleted")
    return a


def _build(a: Application, items: dict[str, int] | None = None):
    return build_quote(a.items if items is None else items, to_business(a.session.profile), TODAY,
                       a.contract_months, a.setup_months, a.discount_pct)


def _quote(a: Application) -> dict:
    return quote_view(_build(a))


def _plan_view(a: Application) -> dict:
    """Quote for the owner's current choices, plus the price of each tier and of every suggested product."""
    q, cat, rec = _build(a), load_catalogue(), a.session.recommendation
    pos = price_position(q.contract_months, q.min_contract_months)
    tiers, seen = [], set()
    for name, items in rec.tiers().items():
        key = frozenset(items.items())
        if key not in seen:   # Basic is often the same as Recommended: show it once
            seen.add(key)
            tiers.append({"id": name, "count": len(items), "monthly_with_gst": _build(a, items).monthly_with_gst})
    return {"quote": quote_view(q), "items": a.items, "tier": a.tier, "tiers": tiers,
            "callback_requested": a.callback is not None,
            "unit_prices": {pk.product_id: unit_price(cat[pk.product_id], pos) for pk in rec.core + rec.addons}}


def _gst_registered(a: Application) -> bool:
    """Owners who said they have no GST (or whose GST is cancelled/suspended) need no GST certificate.
    Not asked yet (no chat) counts as registered, so the full document set is required."""
    return a.session.profile.gstin_status not in ("none", "inactive")


def _status(a: Application) -> dict:
    p = a.session.profile
    return {
        "id": a.id, "language": a.language, "profile": p.safe_view(), "accepted": a.accepted,
        "consent": a.consent.__dict__ if a.consent else None,
        "quote": _quote(a) if a.items else None,
        "documents": {t_: {"uploaded": t_ in a.docs, "required": t_ in required_documents(_gst_registered(a))}
                      for t_ in DOC_TYPES},
        "udyam_number": mask(a.udyam_number),
        "kyc": result_view(a.kyc, a.language) if a.kyc else None,
        "timeline": a.timeline,
    }


# ---------- general ----------
@app.get("/api/health")
def health():
    return {"status": "ok", "advisor_mode": advisor.mode, "today": TODAY.isoformat(), "languages": LANGUAGES,
            "voice_languages": list(VOICE_LANGUAGES) if transcriber.available else []}


@app.get("/api/i18n/{lang}")
def strings(lang: str):
    """Fixed screen text for the phone app (consent, document names, KYC messages)."""
    if lang not in LANGUAGES:
        raise HTTPException(404, "language not supported")
    return {**_strings("en"), **_strings(lang)}


@app.get("/api/catalogue")
def catalogue():
    return {pid: {"name": p.name, "unit": p.unit, "price": p.price, "price_range": [p.price_min, p.price_max]}
            for pid, p in load_catalogue().items()}


# ---------- advisor chat and quote ----------
@app.post("/api/applications")
def start(body: StartBody):
    session, out = advisor.start(body.language)
    a = store.create(session)
    a.mark("chat_started", language=session.profile.language)
    return {"id": a.id, **out}


@app.post("/api/applications/{app_id}/message")
def message(app_id: str, body: MessageBody):
    a = _app(app_id)
    text = (body.text or "").strip()[:MAX_MESSAGE_CHARS]
    if body.slot is None and not text:
        raise HTTPException(422, "Empty message")
    with a.lock:   # two quick taps on one phone must not answer two questions at once
        if a.session.recommendation:
            raise HTTPException(409, "Advice is finished; switch add-ons or accept the quote")
        out = advisor.handle(a.session, text=text, slot=body.slot, value=body.value)
        if out.get("recommendation"):
            a.items = a.session.recommendation.items()
            a.mark("quote_ready", monthly=out["recommendation"]["quote"]["monthly_with_gst"])
    return out


@app.post("/api/applications/{app_id}/voice")
def voice_answer(app_id: str, file: UploadFile = File(...)):
    """A spoken answer -> text, returned to the owner's screen to check before sending (see voice.py on privacy)."""
    a = _app(app_id)
    lang = a.language
    if lang not in VOICE_LANGUAGES or not transcriber.available:
        raise HTTPException(404, "Voice is not available in this language")
    if a.session.recommendation:
        raise HTTPException(409, "Advice is finished; switch add-ons or accept the quote")
    if a.session.profile.gstin_status is None:   # the GST number is always typed, never spoken
        raise HTTPException(409, t(lang, "msg.voice_type_gst"))
    data = file.file.read(MAX_AUDIO_BYTES + 1)
    try:
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(413, t(lang, "msg.voice_too_long"))
        if len(data) < 1000:   # a tap without speech
            raise HTTPException(422, t(lang, "msg.voice_failed"))
        text = transcriber.transcribe(data, file.content_type or "", lang)
    except VoiceUnavailable:
        raise HTTPException(503, t(lang, "msg.voice_failed"))
    finally:
        del data   # the recording is never stored
    if not text:
        raise HTTPException(422, t(lang, "msg.voice_failed"))
    return {"text": text[:MAX_MESSAGE_CHARS]}


@app.post("/api/applications/{app_id}/addons")
def switch_addon(app_id: str, body: AddonBody):
    a = _app(app_id)
    rec = a.session.recommendation
    if not rec or a.accepted:
        raise HTTPException(409, "No open quote to change")
    allowed = {p.product_id: p.quantity for p in rec.core + rec.addons}
    if body.product_id not in allowed:
        raise HTTPException(422, "Only the suggested products can be switched")
    lang, cat = a.language, load_catalogue()
    with a.lock:
        items, _ = toggle(a.items, body.product_id, body.on, allowed[body.product_id])
        q = build_quote(items, to_business(a.session.profile), TODAY)
        # refuse rather than quote a bundle that can't work; a plan that has an internet line keeps one
        # (mobile-only plans are chosen in the chat, so their extras can still be switched)
        lost_line = INTERNET_LINES & set(a.items) and not INTERNET_LINES & set(items)
        if lost_line or not items or not q.valid:
            raise HTTPException(422, t(lang, "msg.cannot_switch_off"))
        notes = [t(lang, "msg.also_removed", product=cat[pid].name, needs=cat[body.product_id].name)
                 for pid in a.items if pid not in items and pid != body.product_id]
        a.items, a.tier = items, "custom"
    return {**_plan_view(a), "notes": notes}


@app.post("/api/applications/{app_id}/price-request")
def price_request(app_id: str):
    """Owner taps 'Ask for a lower price'. Offers come from pricing_settings.json, never from the AI, and never go
    below the catalogue minimum. When there is nothing more to offer, the owner is offered a salesperson's call."""
    a = _app(app_id)
    if not a.session.recommendation or a.accepted:
        raise HTTPException(409, "No open quote to change")
    lang, hours = a.language, price_settings()["sales_callback_hours"]
    with a.lock:
        before = build_quote(a.items, to_business(a.session.profile), TODAY, a.contract_months, a.setup_months)
        room = room_pct(before.list_total, before.floor_total)
        a.price_asks += 1
        offer = next_offer(a.price_asks, room, a.discount_pct)
        if offer is None:
            a.mark("price_handoff", asks=a.price_asks, best_pct=a.discount_pct)
            key = "msg.price.floor" if a.discount_pct == 0 and room < 0.5 else "msg.price.handoff"
            return {**_plan_view(a), "status": "handoff", "message": t(lang, key, hours=hours)}
        a.discount_pct = offer
        q = _build(a)
        last = is_last_offer(a.price_asks, room, a.discount_pct)
        a.mark("price_offer", pct=q.discount_pct, monthly=q.monthly_with_gst)
        message = t(lang, "msg.price.final" if last else "msg.price.offer",
                    pct=f"{q.discount_pct:g}", total=rupees(q.monthly_with_gst))
        return {**_plan_view(a), "status": "final" if last else "offer", "message": message}


@app.post("/api/applications/{app_id}/sales-callback")
def sales_callback(app_id: str, body: CallbackBody):
    """The owner wants a lower price than the chatbot may give: a salesperson calls them. The phone number is used
    only for that call, shown only in the back office, masked everywhere else, and erased with the application."""
    a = _app(app_id)
    lang, hours = a.language, price_settings()["sales_callback_hours"]
    if not body.consent:
        raise HTTPException(422, t(lang, "msg.callback_consent_required"))
    phone = clean_phone(body.phone)
    if not phone:
        raise HTTPException(422, t(lang, "msg.phone_invalid"))
    target = body.target_monthly if body.target_monthly and 0 < body.target_monthly < 10_000_000 else None
    q = _quote(a) if a.items else None
    a.callback = {"phone": phone, "target_monthly": target, "language": lang,
                  "offered_monthly": q["monthly_with_gst"] if q else None, "discount_pct": a.discount_pct,
                  "consent": t(lang, "ui.callback_consent"), "requested_at": date.today().isoformat()}
    a.mark("sales_callback_requested", phone=mask(phone), target_monthly=target)
    ref = a.id[:6].upper()
    return {"ok": True, "reference": ref, "message": t(lang, "msg.callback_ok", hours=hours, ref=ref)}


@app.post("/api/applications/{app_id}/plan")
def choose_plan(app_id: str, body: PlanBody):
    """Pick a tier, a contract length and how to pay the setup fee. An empty body returns the current plan."""
    a = _app(app_id)
    rec = a.session.recommendation
    if not rec:
        raise HTTPException(409, "No quote yet")
    if a.accepted and (body.tier or body.contract_months or body.setup_months):
        raise HTTPException(409, "No open quote to change")
    with a.lock:
        if body.tier:
            tiers = rec.tiers()
            if body.tier not in tiers:
                raise HTTPException(422, "Unknown plan")
            a.items, a.tier = tiers[body.tier], body.tier
        if body.contract_months is not None:
            a.contract_months = body.contract_months   # raised to the bundle's minimum when priced
        if body.setup_months is not None:
            a.setup_months = body.setup_months         # ignored unless 1, 6 or 12 and within the contract
        return _plan_view(a)


@app.post("/api/applications/{app_id}/accept")
def accept(app_id: str):
    a = _app(app_id)
    if not a.items:
        raise HTTPException(409, "No quote yet")
    a.accepted = True
    q = _quote(a)
    a.mark("quote_accepted", monthly=q["monthly_with_gst"], expected_live=q["expected_live"], tier=a.tier,
           contract_months=q["contract_months"], setup_months=q["setup_months"], discount_pct=q["discount_pct"])
    return _status(a)


# ---------- consent and KYC ----------
@app.get("/api/consent/{lang}")
def consent_text(lang: str):
    return {"title": t(lang, "consent.title"), "body": t(lang, "consent.body"), "agree": t(lang, "consent.agree"),
            "purposes": [{"id": p, "text": t(lang, f"consent.purpose.{p}"), "required": p == "kyc"}
                         for p in CONSENT_PURPOSES]}


@app.post("/api/applications/{app_id}/consent")
def give_consent(app_id: str, body: ConsentBody):
    a = _app(app_id)
    if "kyc" not in body.purposes:
        raise HTTPException(422, t(a.language, "consent.required"))
    a.consent = Consent([p for p in body.purposes if p in CONSENT_PURPOSES], a.language)
    a.mark("consent_given", purposes=",".join(a.consent.purposes), version=a.consent.version)
    return _status(a)


def _require_consent(a: Application) -> None:
    if not a.consent:
        raise HTTPException(403, t(a.language, "consent.required"))


@app.post("/api/applications/{app_id}/documents/{doc_type}")
def upload(app_id: str, doc_type: str, file: UploadFile = File(...)):
    """Read one document photo now, so a blurred or wrong photo can be retaken straight away."""
    a = _app(app_id)
    _require_consent(a)
    if doc_type not in DOC_TYPES:
        raise HTTPException(404, "unknown document type")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Photo is larger than 8 MB")
    try:
        doc = read_document(doc_type, data)
    except NotAnImage:
        raise HTTPException(415, "Please upload a photo (JPG or PNG)")
    finally:
        del data   # the photo is never stored: only the fields read from it are kept
    a.docs[doc_type] = doc
    a.kyc = None   # documents changed: decision must be made again
    lang = a.language
    if doc.wrong_type and not doc.blurred:
        ok, msg = False, owner_message(Issue(f"{doc_type}_wrong_document", "RETAKE", doc_type, ""), lang)
    elif doc.blurred or not doc.fields or doc.unread:
        ok, msg = False, owner_message(Issue(f"{doc_type}_unreadable", "RETAKE", doc_type, ""), lang)
    else:
        ok, msg = True, t(lang, "kyc.doc_ok", doc=t(lang, f"doc.{doc_type}"))
    a.mark("document_read", doc=doc_type, ok=ok, seconds=doc.seconds)
    return {"doc_type": doc_type, "ok": ok, "message": msg, "fields": masked_fields(doc),
            "straightened": bool(doc.tilt)}


@app.post("/api/applications/{app_id}/udyam-number")
def udyam_number(app_id: str, body: UdyamBody):
    a = _app(app_id)
    _require_consent(a)
    a.udyam_number = clean_id(body.number)
    a.kyc = None
    return {"udyam_number": mask(a.udyam_number)}


@app.post("/api/applications/{app_id}/kyc")
def submit_kyc(app_id: str):
    a = _app(app_id)
    _require_consent(a)
    p = a.session.profile
    a.kyc = assess(dict(a.docs), KycContext(TODAY, claimed_gstin=p.gstin, udyam_number=a.udyam_number,
                                                gst_registered=_gst_registered(a)))
    a.mark("kyc_checked", decision=a.kyc.decision, issues=",".join(a.kyc.codes))
    if a.kyc.decision == "PASS" and a.accepted:
        a.mark("installation_booked", expected_live=_quote(a)["expected_live"])
    return result_view(a.kyc, a.language)


# ---------- tracker and privacy ----------
@app.get("/api/applications/{app_id}")
def status(app_id: str):
    return _status(_app(app_id))


@app.delete("/api/applications/{app_id}")
def erase(app_id: str):
    a = _app(app_id)
    lang = a.language
    store.erase(app_id)
    return {"deleted": True, "message": t(lang, "privacy.deleted")}


# ---------- back office (needs BACKOFFICE_KEY in .env; off when unset) ----------
@app.get("/api/backoffice/applications")
def backoffice(x_admin_key: str | None = Header(default=None)):
    key = os.getenv("BACKOFFICE_KEY")
    if not key or x_admin_key != key:
        raise HTTPException(401, "back office key required")
    out = []
    for a in store.all():
        p = a.session.profile
        out.append({"id": a.id[:6], "business": p.business_name or p.business_type, "city": p.city,
                    "kind": p.segment, "gstin": mask(p.gstin), "accepted": a.accepted,
                    "monthly": _quote(a)["monthly_with_gst"] if a.items else None,
                    "documents": {k: masked_fields(d) for k, d in a.docs.items()},
                    "kyc": result_view(a.kyc, "en", back_office=True) if a.kyc else None,
                    "price": {"asks": a.price_asks, "discount_pct": a.discount_pct, "tier": a.tier},
                    # leads the chatbot could not close: the full number is shown here only, so sales can call
                    "sales_callback": {**a.callback, "reference": a.id[:6].upper()} if a.callback else None,
                    "timeline": a.timeline})
    return sorted(out, key=lambda x: x["sales_callback"] is None)   # calls to make come first


# ---------- the built phone app (frontend/dist), served from the same address ----------
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="app")

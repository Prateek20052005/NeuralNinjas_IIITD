"""HTTP API for the phone web app: advisor chat -> quote with add-on switches -> consent -> KYC -> tracker.

Run: .venv/Scripts/python -m uvicorn backend.app.main:app --reload
All state is per application id (an unguessable token the phone keeps). See store.py for privacy rules.
"""
from __future__ import annotations

import csv
import hmac
import logging
import os
import re
import threading
from collections import Counter
from functools import lru_cache
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .advisor.engine import Advisor, quote_view, recommendation_view
from .advisor.flow import next_slot, question, to_business
from .catalogue import DATA_DIR, INTERNET_LINES, load_catalogue
from .predictor import leads_to_call, model as predictor_model, score_application
from .bundles import top_rules
from .i18n import LANGUAGES, _strings, t
from .kyc.checks import Issue, KycContext, assess, required_documents
from .kyc.documents import DOC_TYPES, read_document
from .kyc.lookups import clean_id, mask
from .kyc.messages import owner_message, result_view
from .kyc.ocr import NotAnImage
from .negotiate import clean_phone, negotiation_step, room_pct, rupees, settings as price_settings
from .quote import build_quote, contract_options, price_position, toggle, unit_price
from .voice import MAX_AUDIO_BYTES, VOICE_LANGUAGES, Transcriber, VoiceUnavailable
from .store import CONSENT_PURPOSES, Application, Consent, Store, case_clock, masked_fields
from .otp import OtpError, check as check_code, demo_mode, issue as issue_code
from .sms import SmsError, missing_settings as sms_missing, provider as sms_provider, send_code as send_sms

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
_APP_PATH = re.compile(r"^/api/applications/([A-Za-z0-9_-]+)")


@app.middleware("http")
async def save_progress(request: Request, call_next):
    """Every change to an application is saved (encrypted) so a server restart doesn't lose the owner's progress."""
    response = await call_next(request)
    m = _APP_PATH.match(request.url.path)
    if m and request.method in ("POST", "PUT", "DELETE") and response.status_code < 500:
        store.save(m.group(1))
    return response
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
advisor = Advisor(order_date=TODAY)
transcriber = Transcriber(advisor.llm.client)   # voice answers use the same Groq key as the chat
store = Store()
log = logging.getLogger("api")

# The conversion predictor trains on the 5,000 past leads in a few seconds; do it in the background at start-up so
# the owner app is never slowed down. Staff pages show "starting up" until it is ready.
predictor_ready = threading.Event()


def _warm_predictor() -> None:
    try:
        metrics = predictor_model().metrics
        predictor_ready.set()
        log.info("conversion predictor ready: AUC %.3f on %d unseen leads", metrics["auc"], metrics["test_leads"])
    except Exception:
        log.exception("conversion predictor could not be trained; staff pages run without scores")


threading.Thread(target=_warm_predictor, daemon=True).start()

if not demo_mode() and sms_missing():   # say it at start-up, not at the first owner's failed code
    log.error("OTP_MODE=sms but SMS is not set up (missing %s): codes cannot be sent", ", ".join(sms_missing()))


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
    billing_months: int | None = None     # pay every 1, 3, 6 or 12 months


class CallbackBody(BaseModel):
    phone: str
    consent: bool                         # "call me about the price of this plan"
    target_monthly: int | None = None     # price that would work for the owner, if they said


class AddonBody(BaseModel):
    product_id: str
    on: bool          # switched on at the suggested quantity


class ConsentBody(BaseModel):
    purposes: list[str]


class PhoneBody(BaseModel):
    phone: str
    lang: str = "en"          # for "continue a saved application", picked on the home screen


class CodeBody(BaseModel):
    code: str
    marketing: bool = False   # separate, optional: offers and news from Accel Business


class ResumeCodeBody(BaseModel):
    phone: str
    code: str
    lang: str = "en"


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
                       a.contract_months, a.setup_months, a.discount_pct, a.billing_months, _first_time(a))


def _first_time(a: Application) -> bool:
    """Welcome offer: only for businesses not already with Accel (our records for a GSTIN, the owner's answer otherwise)."""
    return a.session.profile.existing_customer is False


def _quote(a: Application) -> dict:
    return quote_view(_build(a))


def _plan_view(a: Application) -> dict:
    """Quote for the owner's current choices, plus the price of each tier and of every suggested product."""
    q, cat, rec = _build(a), load_catalogue(), a.session.recommendation
    pos = price_position(q.contract_months, q.min_contract_months)
    tiers, seen = [], set()
    # Basic is often the same as Recommended: show it once, as "Recommended" (the plan the owner starts on, so one
    # card is always selected), and keep the cards in Basic -> Recommended -> Full order
    for name in ("recommended", "basic", "full"):
        items = rec.tiers()[name]
        key = frozenset(items.items())
        if key not in seen:
            seen.add(key)
            tiers.append({"id": name, "count": len(items), "monthly_with_gst": _build(a, items).monthly_with_gst})
    tiers.sort(key=lambda t: ("basic", "recommended", "full").index(t["id"]))
    return {"quote": quote_view(q), "items": a.items, "tier": a.tier, "tiers": tiers,
            "callback_requested": a.callback is not None,
            "unit_prices": {pk.product_id: unit_price(cat[pk.product_id], pos) for pk in rec.core + rec.addons}}


def _gst_registered(a: Application) -> bool:
    """Owners who said they have no GST need no GST or Udyam certificate (small businesses don't have to register).
    A cancelled or suspended GSTIN is different: the certificate is still required and checked against the registry,
    so it is rejected like K01 in the answer key. Not asked yet (no chat) counts as registered."""
    return a.session.profile.gstin_status != "none"


def _status(a: Application) -> dict:
    p = a.session.profile
    return {
        "id": a.id, "language": a.language, "profile": p.safe_view(), "accepted": a.accepted,
        "consent": a.consent.__dict__ if a.consent else None,
        "quote": _quote(a) if a.items else None,
        "documents": {t_: {"uploaded": t_ in a.docs, "required": t_ in required_documents(_gst_registered(a)),
                           # the owner's own details, masked like everywhere else (shown on the privacy page)
                           "fields": masked_fields(a.docs[t_]) if t_ in a.docs else {},
                           **(dict(zip(("ok", "message"), _doc_check(t_, a.docs[t_], a.language))) if t_ in a.docs else {})}
                      for t_ in DOC_TYPES},
        "udyam_number": mask(a.udyam_number),
        "kyc": result_view(a.kyc, a.language) if a.kyc else None,
        "timeline": a.timeline,
        # privacy page: everything is erased automatically after this much time without activity
        "phone": mask(a.phone), "phone_verified": bool(a.phone_verified_at), "marketing_consent": a.marketing_consent,
        "retention_hours": round(store.retention.total_seconds() / 3600),
        "delete_after": case_clock(a.last_seen + store.retention).isoformat(timespec="minutes"),
    }


# ---------- general ----------
@app.get("/api/health")
def health():
    return {"status": "ok", "advisor_mode": advisor.mode, "today": TODAY.isoformat(), "languages": LANGUAGES,
            "voice_languages": list(VOICE_LANGUAGES) if transcriber.available else [],
            "progress_saved": store.saving, "otp_demo": demo_mode(),
            "sms": None if demo_mode() else {"provider": sms_provider() or None, "ready": not sms_missing()}}


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
            if a.accepted:
                raise HTTPException(409, "The plan is accepted; carry on with the documents")
            return _after_plan(a, text)
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
    if not transcriber.available:
        raise HTTPException(503, "Voice input is switched off on this server")
    if lang not in VOICE_LANGUAGES:
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


def _after_plan(a: Application, text: str) -> dict:
    """The chat stays open after the plan: product questions get an answer, and price requests are negotiated.
    Asking for a lower price first gets no discount, only the honest ways to pay less (Basic plan, longer contract);
    if the owner insists, 5% and then 10% (pricing_settings.json), then a salesperson's call. Amounts always come
    from negotiate.py and never go below the catalogue minimum; the AI only helps tell that a message is a request."""
    lang = a.language
    plan = {"question": None, "mode": advisor.mode}
    if not text:   # a stale tap on an old question
        return {**plan, "messages": [t(lang, "msg.plan_ready")]}
    price, say = advisor.after_plan(a.session, text)
    if not price:
        return {**plan, "messages": [say or t(lang, "msg.plan_ready")]}

    hours = price_settings()["sales_callback_hours"]
    before = build_quote(a.items, to_business(a.session.profile), TODAY, a.contract_months, a.setup_months)
    room = room_pct(before.list_total, before.floor_total)
    a.price_asks += 1
    step, pct = negotiation_step(a.price_asks, room, a.discount_pct)
    if step == "pushback":
        msgs = [t(lang, "msg.price.pushback")] + _cheaper_ways(a)
        a.mark("price_pushback", asks=a.price_asks)
    elif step == "handoff":
        key = "msg.price.floor" if a.discount_pct == 0 and room < 0.5 else "msg.price.handoff"
        msgs = [t(lang, key, hours=hours)]
        a.mark("price_handoff", asks=a.price_asks, best_pct=a.discount_pct)
    else:
        a.discount_pct = pct
        q = _build(a)
        msgs = [t(lang, f"msg.price.{step}", pct=f"{q.discount_pct:g}", total=rupees(q.monthly_with_gst))]
        a.mark("price_offer", pct=q.discount_pct, monthly=q.monthly_with_gst)
    return {**plan, "messages": msgs, "negotiation": {"status": step}, "quote": quote_view(_build(a))}


def _cheaper_ways(a: Application) -> list[str]:
    """Honest ways to pay less without a discount: the Basic plan, and a longer contract (both at list prices)."""
    lang, now = a.language, _build(a).monthly_with_gst
    out = []
    basic = a.session.recommendation.tiers()["basic"]
    if basic != a.items and (b := _build(a, basic).monthly_with_gst) < now:
        out.append(t(lang, "msg.price.alt_basic", total=rupees(b)))
    longer = [o for o in _build(a).contract_options if o["monthly_with_gst"] < now]
    if longer:
        best = min(longer, key=lambda o: o["monthly_with_gst"])
        out.append(t(lang, "msg.price.alt_contract", months=best["months"], total=rupees(best["monthly_with_gst"])))
    return out


@app.post("/api/applications/{app_id}/sales-callback")
def sales_callback(app_id: str, body: CallbackBody):
    """The owner wants a lower price than the chatbot may give: a salesperson calls them. The phone number is used
    only for that call, shown only in the back office, masked everywhere else, and erased with the application."""
    a = _app(app_id)
    if not a.session.recommendation or a.accepted:
        raise HTTPException(409, "No open quote to change")
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
                  "consent": t(lang, "ui.callback_consent"), "requested_at": TODAY.isoformat()}
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
    if a.accepted and (body.tier or body.contract_months or body.setup_months or body.billing_months):
        raise HTTPException(409, "No open quote to change")
    with a.lock:
        if body.tier:
            tiers = rec.tiers()
            if body.tier not in tiers:
                raise HTTPException(422, "Unknown plan")
            a.items, a.tier = tiers[body.tier], body.tier
        if body.contract_months is not None:
            if body.contract_months not in contract_options(a.items):
                raise HTTPException(422, "Choose one of the contract lengths shown")
            a.contract_months = body.contract_months
        if body.setup_months is not None:
            if body.setup_months not in (1, 6, 12):
                raise HTTPException(422, "Setup can be paid at once or over 6 or 12 months")
            a.setup_months = body.setup_months         # ignored if longer than the contract
        if body.billing_months is not None:
            if body.billing_months not in [o["months"] for o in _build(a).billing_options]:
                raise HTTPException(422, "Choose one of the billing options shown")
            a.billing_months = body.billing_months
        return _plan_view(a)


@app.post("/api/applications/{app_id}/accept")
def accept(app_id: str):
    a = _app(app_id)
    if not a.items:
        raise HTTPException(409, "No quote yet")
    if a.accepted:          # double tap or page reload: already accepted, nothing to record again
        return _status(a)
    if not a.phone_verified_at:   # needed for order updates and the installation visit
        raise HTTPException(409, t(a.language, "msg.phone_required"))
    a.accepted = True
    q = _quote(a)
    a.mark("quote_accepted", monthly=q["monthly_with_gst"], expected_live=q["expected_live"], tier=a.tier,
           contract_months=q["contract_months"], setup_months=q["setup_months"], discount_pct=q["discount_pct"],
           billing_months=q["billing_months"], first_time=bool(q["welcome"]), setup_due=q["setup_due"])
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


def _doc_check(doc_type: str, doc, lang: str) -> tuple[bool, str]:
    """Was this photo good enough? Same answer right after upload and later in the status (after a reload)."""
    if doc.wrong_type and not doc.blurred:
        return False, owner_message(Issue(f"{doc_type}_wrong_document", "RETAKE", doc_type, ""), lang)
    if doc.blurred or not doc.fields or doc.unread:
        return False, owner_message(Issue(f"{doc_type}_unreadable", "RETAKE", doc_type, ""), lang)
    return True, t(lang, "kyc.doc_ok", doc=t(lang, f"doc.{doc_type}"))


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
    ok, msg = _doc_check(doc_type, doc, a.language)
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
# ---------- mobile number: save progress, continue on another phone, required to accept ----------
def _otp_error(e: OtpError, lang: str) -> HTTPException:
    return HTTPException(429 if e.code in ("wait", "too_many") else 422, t(lang, f"msg.otp_{e.code}", seconds=e.seconds))


def _phone(raw: str, lang: str) -> str:
    phone = clean_phone(raw)
    if not phone:
        raise HTTPException(422, t(lang, "msg.phone_invalid"))
    return phone


def _deliver(phone: str, code: str, lang: str) -> dict:
    """Demo mode: the code goes back to the screen (for judging). SMS mode: it is texted and never returned."""
    if demo_mode():
        return {"sent": True, "phone": mask(phone), "demo_code": code}
    try:
        send_sms(phone, code, t(lang, "msg.otp_sms", code=code))
    except SmsError:
        raise HTTPException(503, t(lang, "msg.otp_send_failed"))
    return {"sent": True, "phone": mask(phone)}


@app.post("/api/applications/{app_id}/phone")
def send_phone_code(app_id: str, body: PhoneBody):
    a = _app(app_id)
    phone = _phone(body.phone, a.language)
    with a.lock:
        try:
            record, code = issue_code(a.otp, phone)
        except OtpError as e:
            raise _otp_error(e, a.language)
        sent = _deliver(phone, code, a.language)   # kept only once it is sent: a failed SMS costs no wait or try
        a.otp = record
    return sent


@app.post("/api/applications/{app_id}/phone/verify")
def verify_phone(app_id: str, body: CodeBody):
    a = _app(app_id)
    with a.lock:
        try:
            phone = check_code(a.otp, body.code)
        except OtpError as e:
            raise _otp_error(e, a.language)
        a.phone, a.phone_verified_at = phone, case_clock().isoformat(timespec="seconds")
        a.marketing_consent = bool(body.marketing)
        a.mark("phone_verified", phone=mask(phone), marketing=a.marketing_consent)
    return {"verified": True, "phone": mask(phone), "marketing_consent": a.marketing_consent}


@app.post("/api/resume")
def send_resume_code(body: PhoneBody):
    """Continue a saved application on any phone. The answer is the same whether or not the number has one,
    so nobody can find out which numbers have applications."""
    lang = body.lang if body.lang in LANGUAGES else "en"
    phone = _phone(body.phone, lang)
    try:
        record, code = issue_code(store.resume_codes.get(phone), phone)
    except OtpError as e:
        raise _otp_error(e, lang)
    sent = _deliver(phone, code, lang)
    store.resume_codes[phone] = record
    return sent


@app.post("/api/resume/verify")
def resume(body: ResumeCodeBody):
    lang = body.lang if body.lang in LANGUAGES else "en"
    phone = _phone(body.phone, lang)
    try:
        check_code(store.resume_codes.get(phone), body.code)
    except OtpError as e:
        raise _otp_error(e, lang)
    store.resume_codes.pop(phone, None)
    a = store.find_by_phone(phone)
    if not a:
        raise HTTPException(404, t(lang, "msg.resume_none", hours=round(store.retention.total_seconds() / 3600)))
    a.mark("resumed")
    store.save(a.id)
    return _snapshot(a)


def _snapshot(a: Application) -> dict:
    """What a phone needs to pick up an application. The chat transcript is not kept, so the chat restarts with
    "welcome back" and the next question; plan, documents and tracker come back as they were."""
    s, lang = a.session, a.language
    rec = recommendation_view(s.recommendation, s.explanation) if s.recommendation else None
    slot = None if rec else next_slot(s.profile)
    q = question(s.profile, slot) if slot else None
    screen = ("tracker" if a.kyc else "documents" if a.consent else "consent" if a.accepted
              else "plan" if rec else "chat")
    texts = [t(lang, "msg.welcome_back")] + ([q["text"]] if q else [t(lang, "msg.plan_ready")] if rec else [])
    return {"id": a.id, "lang": lang, "screen": screen, "question": q, "rec": rec, "items": a.items,
            "accepted": a.accepted, "consented": bool(a.consent), "phoneVerified": bool(a.phone_verified_at),
            "phoneSaved": mask(a.phone), "messages": [{"from": "bot", "text": x} for x in texts]}


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
def _staff(x_admin_key: str | None) -> None:
    key = os.getenv("BACKOFFICE_KEY")
    if not key or not x_admin_key or not hmac.compare_digest(x_admin_key, key):
        raise HTTPException(401, "back office key required")


def _score(a: Application) -> dict | None:
    """Conversion score for a live application (predictor.py); None while the predictor is still warming up."""
    try:
        return score_application(a.session.profile) if predictor_ready.is_set() else None
    except Exception:   # the score is a hint for staff; never let it break the page
        log.exception("conversion score failed")
        return None


@app.get("/api/backoffice/applications")
def backoffice(x_admin_key: str | None = Header(default=None)):
    _staff(x_admin_key)
    out = []
    for a in store.all():
        p = a.session.profile
        out.append({"id": a.id[:6], "business": p.business_name or p.business_type, "city": p.city,
                    "kind": p.segment, "gstin": mask(p.gstin), "accepted": a.accepted,
                    "monthly": _quote(a)["monthly_with_gst"] if a.items else None,
                    "documents": {k: masked_fields(d) for k, d in a.docs.items()},
                    "kyc": result_view(a.kyc, "en", back_office=True) if a.kyc else None,
                    "price": {"asks": a.price_asks, "discount_pct": a.discount_pct, "tier": a.tier,
                              "billing_months": a.billing_months, "first_time": _first_time(a)},
                    "phone": mask(a.phone), "marketing_consent": a.marketing_consent,
                    "conversion": None if a.accepted else _score(a),
                    # leads the chatbot could not close: the full number is shown here only, so sales can call
                    "sales_callback": {**a.callback, "reference": a.id[:6].upper()} if a.callback else None,
                    "timeline": a.timeline})
    return sorted(out, key=lambda x: x["sales_callback"] is None)   # calls to make come first


HISTORY_STAGES = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]


@lru_cache(maxsize=1)
def _history() -> dict:
    """The old, sales-led funnel from the leads file (Apr-Jun 2026), to compare the app against."""
    with open(DATA_DIR / "smb_leads.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    reached = Counter(HISTORY_STAGES.index(r["stage_reached"]) for r in rows)
    funnel = [{"stage": st, "count": sum(n for i, n in reached.items() if i >= k)} for k, st in enumerate(HISTORY_STAGES)]
    days = [int(r["days_lead_to_activation"]) for r in rows if r["days_lead_to_activation"]]
    return {"funnel": funnel, "avg_days_to_activate": round(sum(days) / len(days), 1),
            "top_drop_reasons": [{"reason": k, "count": n} for k, n in
                                 Counter(r["drop_reason"] for r in rows if r["drop_reason"]).most_common(6)]}


@app.get("/api/backoffice/stats")
def backoffice_stats(x_admin_key: str | None = Header(default=None)):
    """Live numbers from the app's applications, the old funnel for comparison, and how good the predictor is."""
    _staff(x_admin_key)
    apps = store.all()
    steps = [{s["step"] for s in a.timeline} for a in apps]
    accepted = [a for a in apps if a.accepted]
    quotes = [_quote(a) for a in accepted]
    funnel = [("Started a chat", len(apps)),
              ("Got a plan", sum("quote_ready" in s for s in steps)),
              ("Accepted the plan", len(accepted)),
              ("Gave consent", sum("consent_given" in s for s in steps)),
              ("KYC passed", sum(1 for a in apps if a.kyc and a.kyc.decision == "PASS")),
              ("Installation booked", sum("installation_booked" in s for s in steps))]
    monthly = sum(q["monthly_with_gst"] for q in quotes)
    return {
        "funnel": [{"stage": k, "count": n} for k, n in funnel],
        "money": {"monthly_with_gst": monthly, "average_monthly": round(monthly / len(quotes)) if quotes else 0,
                  "setup_due": sum(q["setup_due"] for q in quotes)},
        "offers": {"discounted": sum(1 for a in apps if a.discount_pct), "callbacks": sum(1 for a in apps if a.callback),
                   "welcome": sum(1 for q in quotes if q["welcome"]),
                   "pay_ahead": sum(1 for q in quotes if q["billing_months"] > 1),
                   "marketing_ok": sum(1 for a in apps if a.marketing_consent)},
        "kyc": dict(Counter(a.kyc.decision for a in apps if a.kyc)),
        "languages": dict(Counter(LANGUAGES.get(a.language, a.language) for a in apps)),
        "kinds": dict(Counter(a.session.profile.segment or "not yet" for a in apps)),
        "history": _history(),
        "predictor": predictor_model().metrics if predictor_ready.is_set() else None,
        "sells_together": top_rules(2),   # strongest 'bought together' rules per kind of business (bundles.py)
    }


@app.get("/api/backoffice/customers")
def backoffice_customers(x_admin_key: str | None = Header(default=None)):
    """Owners who accepted a plan: what they bought and on what terms (phone masked; marketing only if they agreed)."""
    _staff(x_admin_key)
    out = []
    for a in store.all():
        if not a.accepted:
            continue
        p, q = a.session.profile, _quote(a)
        when = next((s["at"] for s in a.timeline if s["step"] == "quote_accepted"), None)
        out.append({"ref": a.id[:6].upper(), "business": p.business_name or p.business_type, "city": p.city,
                    "kind": p.segment, "language": LANGUAGES.get(a.language, a.language),
                    "plan": [f"{l['name']} ×{l['quantity']}" if l["quantity"] > 1 else l["name"] for l in q["lines"]],
                    "monthly_with_gst": q["monthly_with_gst"], "contract_months": q["contract_months"],
                    "billing_months": q["billing_months"], "setup_due": q["setup_due"],
                    "discount_pct": q["discount_pct"], "welcome": bool(q["welcome"]), "tier": a.tier,
                    "phone": mask(a.phone), "marketing_consent": a.marketing_consent,
                    "kyc": a.kyc.decision if a.kyc else None, "accepted_at": when})
    return sorted(out, key=lambda c: c["accepted_at"] or "", reverse=True)


@app.get("/api/backoffice/leads")
def backoffice_leads(limit: int = 50, x_admin_key: str | None = Header(default=None)):
    """Conversion predictor: past leads that dropped for a reason the app now answers, best chance first."""
    _staff(x_admin_key)
    if not predictor_ready.is_set():
        raise HTTPException(503, "The conversion predictor is still starting up. Try again in a few seconds.")
    return {"model": predictor_model().metrics, "leads": leads_to_call(max(1, min(limit, 200)))}


# ---------- the built phone app (frontend/dist), served from the same address ----------
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="app")

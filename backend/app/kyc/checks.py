"""Smart KYC: check one application's documents against the registries, the CRM lead record and each other.

Decision = the most serious issue found:
  REJECT     the documents are invalid or do not belong to this business (cancelled GST, altered certificate)
  RETAKE     the owner can fix it now with a new photo (blurred, expired, bill too old, wrong document)
  INCOMPLETE a document is missing
  REVIEW     a person at Accel must look (signatory not on record, bill in another name)
  PASS       everything matches
Notes never change the decision (OCR repairs, known differences in the specimen Udyam data).

Owners without an active GST registration (the advisor only offers them products that don't need GST) are not
asked for a GST certificate, and Udyam is optional for them: their business name is taken from Udyam if they
have it, otherwise only the address proof and the signatory ID are checked.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from ..catalogue import DATA_DIR
from .documents import DOC_TYPES, ParsedDoc, parse_date
from .lookups import GSTIN_RE, gstin_checksum_ok, lookup_gstin, lookup_udyam, mask

SEVERITY = ["REJECT", "RETAKE", "INCOMPLETE", "REVIEW"]   # most serious first
BILL_MAX_DAYS = 90
GST_STATE_CODES = {"03": "Punjab", "07": "Delhi", "08": "Rajasthan", "19": "West Bengal", "24": "Gujarat",
                   "27": "Maharashtra", "32": "Kerala", "37": "Andhra Pradesh"}


@dataclass
class Issue:
    code: str              # stable id, e.g. "gstin_cancelled" (matches the answer key)
    decision: str          # REJECT / RETAKE / INCOMPLETE / REVIEW / NOTE
    doc: str | None        # which document the owner has to act on
    evidence: str          # for the back office; identifiers masked
    params: dict = field(default_factory=dict)   # for the owner-facing message


@dataclass
class KycResult:
    decision: str
    issues: list[Issue]
    notes: list[Issue]
    gstin: str | None
    lead_id: str | None

    @property
    def codes(self) -> list[str]:
        return [i.code for i in self.issues]


@dataclass
class KycContext:
    today: date
    claimed_gstin: str | None = None      # GSTIN the owner typed in the advisor chat, if any
    udyam_number: str | None = None       # typed instead of uploading the Udyam certificate
    gst_registered: bool = True           # False: owner never registered for GST, so GST and Udyam are optional


def required_documents(gst_registered: bool) -> list[str]:
    return list(DOC_TYPES) if gst_registered else ["address_proof", "signatory_id"]


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


@lru_cache(maxsize=1)
def _leads() -> list[dict]:
    with open(DATA_DIR / "smb_leads.csv", encoding="utf-8") as f:
        return [{k: r[k] for k in ("lead_id", "gstin", "has_udyam", "udyam_number", "contact_name", "contact_role")}
                for r in csv.DictReader(f)]


def find_lead(gstin: str | None, udyam: str | None) -> dict | None:
    for r in _leads():
        if (gstin and r["gstin"] == gstin) or (udyam and r["udyam_number"] == udyam):
            return r
    return None


def assess(docs: dict[str, ParsedDoc | None], ctx: KycContext) -> KycResult:
    issues: list[Issue] = []

    def add(code, decision, doc, evidence, **params):
        issues.append(Issue(code, decision, doc, evidence, params))

    # ---- 1. every document present, readable and of the right type
    usable: dict[str, ParsedDoc] = {}
    required = required_documents(ctx.gst_registered)
    for t in DOC_TYPES:
        d = docs.get(t)
        if d is None:
            if t == "udyam_certificate" and ctx.udyam_number:
                continue  # owner typed the number instead: checked against the registry below
            if t not in required:
                continue  # optional for owners without GST
            add(f"{t}_missing", "INCOMPLETE", t, f"No {t.replace('_', ' ')} uploaded")
        elif d.wrong_type and not d.blurred:
            add(f"{t}_wrong_document", "RETAKE", t, f"Uploaded a {d.detected_type.replace('_', ' ')} here")
        elif d.blurred or not d.fields:
            add(f"{t}_unreadable", "RETAKE", t, f"Photo too blurred to read (sharpness {d.sharpness})")
        elif d.unread:   # printed but not readable (shadow, glare): ask for a new photo, never treat it as blank
            add(f"{t}_unreadable", "RETAKE", t, f"Printed but could not be read: {', '.join(d.unread)}")
        else:
            usable[t] = d
    gst_doc, udy_doc = usable.get("gst_certificate"), usable.get("udyam_certificate")
    bill, sid = usable.get("address_proof"), usable.get("signatory_id")

    # ---- 2. GST certificate vs the GST registry
    reg = None
    gstin = gst_doc.fields.get("gstin") if gst_doc else None
    if gst_doc:
        if not gstin:
            add("gstin_unreadable", "RETAKE", "gst_certificate", "GSTIN not found on the certificate")
        elif not (GSTIN_RE.match(gstin) and gstin_checksum_ok(gstin)):
            near = [g for g in _gst_index() if len(g) == len(gstin) and sum(a != b for a, b in zip(g, gstin)) <= 2]
            add("gstin_checksum_fail", "REJECT", "gst_certificate",
                f"Certificate GSTIN {mask(gstin)} fails the checksum and is not in the registry"
                + (f"; closest registry GSTIN {mask(near[0])}" if near else ""))
        else:
            r = lookup_gstin(gstin)
            if not r.found:
                add("gstin_not_in_registry", "REJECT", "gst_certificate", f"GSTIN {mask(gstin)} not in the registry")
            else:
                reg = r
                if r.status != "Active":   # Suspended is treated like Cancelled
                    add(f"gstin_{r.status.lower()}", "REJECT", "gst_certificate",
                        f"Registry status of {mask(gstin)} is {r.status}", status=r.status)
                for key, reg_val, code in [("legal_name", r.legal_name, "gst_legal_name_mismatch"),
                                           ("trade_name", r.trade_name, "gst_trade_name_mismatch"),
                                           ("address", r.address, "gst_address_mismatch")]:
                    if _norm(gst_doc.fields.get(key)) != _norm(reg_val):
                        add(code, "REJECT", "gst_certificate",
                            f"Certificate says '{gst_doc.fields.get(key)}', registry says '{reg_val}'")
                if _norm(gst_doc.fields.get("liability_date")) != _norm(r.registration_date):
                    add("gst_date_mismatch", "REVIEW", "gst_certificate",
                        f"Certificate date {gst_doc.fields.get('liability_date')} vs registry {r.registration_date}")
                state = GST_STATE_CODES.get(gstin[:2])
                if state and state != r.state:
                    add("gstin_state_mismatch", "REJECT", "gst_certificate",
                        f"State code {gstin[:2]} is {state}, registry state is {r.state}")
        if gstin and ctx.claimed_gstin and gstin != ctx.claimed_gstin:
            # the plan was made for the business the owner named in the chat: the certificate must be that one
            add("gstin_differs_from_application", "RETAKE", "gst_certificate",
                f"Owner typed {mask(ctx.claimed_gstin)} in the chat, certificate shows {mask(gstin)}",
                claimed=mask(ctx.claimed_gstin), found=mask(gstin))
    trade = reg.trade_name if reg else (gst_doc.fields.get("trade_name") if gst_doc else None)

    # ---- 3. Udyam certificate (or typed number) vs the Udyam registry
    udyam = udy_doc.fields.get("udyam_number") if udy_doc else ctx.udyam_number
    if udy_doc or ctx.udyam_number:
        doc = "udyam_certificate"
        if not udyam:
            add("udyam_number_blank", "REJECT", doc, "Udyam number field on the certificate is empty")
        else:
            u = lookup_udyam(udyam)
            if not u.format_ok:
                add("udyam_format_fail", "REJECT", doc, f"'{mask(udyam)}' is not a valid Udyam number")
            elif not u.found:
                add("udyam_not_in_registry", "REJECT", doc, f"Udyam number {mask(udyam)} not in the registry")
            else:
                udyam = u.udyam_number
                if udy_doc:
                    for key, reg_val in [("enterprise_name", u.enterprise_name), ("city", u.city), ("state", u.state)]:
                        if _norm(udy_doc.fields.get(key)) != _norm(reg_val):
                            add(f"udyam_{key}_mismatch", "REJECT", doc,
                                f"Certificate says '{udy_doc.fields.get(key)}', registry says '{reg_val}'")
                    # activity and date differ on almost every specimen certificate (data generator noise)
                    for key, reg_val in [("major_activity", u.major_activity), ("registration_date", u.registration_date)]:
                        if _norm(udy_doc.fields.get(key)) != _norm(reg_val):
                            add(f"udyam_{key}_differs", "NOTE", doc,
                                f"Certificate {udy_doc.fields.get(key)} vs registry {reg_val}")
                if trade and _norm(u.enterprise_name) != _norm(trade):
                    add("udyam_belongs_to_other_business", "REJECT", doc,
                        f"Udyam is for '{u.enterprise_name}', GST is for '{trade}'")
                trade = trade or u.enterprise_name   # no GST certificate: Udyam names the business

    # ---- 4. address proof: right business, right address, recent
    if bill:
        if trade and _norm(bill.fields.get("billed_to")) != _norm(trade):
            add("address_proof_name_mismatch", "REVIEW", "address_proof",
                f"Bill is in the name of '{bill.fields.get('billed_to')}', business is '{trade}'")
        addr = reg.address if reg else (gst_doc.fields.get("address") if gst_doc else None)
        if addr and _norm(bill.fields.get("supply_address")) != _norm(addr):
            add("address_proof_address_mismatch", "REVIEW", "address_proof",
                f"Bill address '{bill.fields.get('supply_address')}' vs registered '{addr}'")
        billed = parse_date(bill.fields.get("bill_date", ""))
        if billed is None:
            add("address_proof_date_unreadable", "RETAKE", "address_proof", "Bill date could not be read")
        elif (ctx.today - billed).days > BILL_MAX_DAYS:
            add("address_proof_too_old", "RETAKE", "address_proof",
                f"Bill dated {billed} is {(ctx.today - billed).days} days old (limit {BILL_MAX_DAYS})",
                days=(ctx.today - billed).days, limit=BILL_MAX_DAYS)
        elif billed > ctx.today:
            add("address_proof_future_date", "REVIEW", "address_proof", f"Bill dated in the future: {billed}")

    # ---- 5. signatory ID: valid, for this business, and a person on record
    # No GST or Udyam (small owners need neither): the bill is the only other proof of the business, so the ID must
    # be for the business named on the bill. Otherwise anyone's bill plus anyone's ID would pass.
    from_bill = not trade and bill is not None and bool(bill.fields.get("billed_to"))
    if from_bill:
        trade = bill.fields["billed_to"]
    lead = find_lead(gstin, udyam)
    if sid:
        valid = parse_date(sid.fields.get("valid_till", ""))
        if valid is None:
            add("signatory_id_validity_unreadable", "RETAKE", "signatory_id", "Expiry date could not be read")
        elif valid < ctx.today:
            add("signatory_id_expired", "RETAKE", "signatory_id", f"ID expired on {valid}")
        if trade and _norm(sid.fields.get("business")) != _norm(trade):
            add("signatory_business_mismatch", "REVIEW", "signatory_id",
                f"ID is for '{sid.fields.get('business')}', "
                + (f"bill is for '{trade}' (no GST or Udyam certificate)" if from_bill else f"business is '{trade}'"))
        name = sid.fields.get("name")
        m = re.match(r"(.+?) \(Prop\.", reg.legal_name if reg else "")
        if m and _norm(name) != _norm(m.group(1)):   # proprietorship: only the proprietor can sign
            add("signatory_not_authorised", "REVIEW", "signatory_id",
                f"ID belongs to {name}; proprietor is {m.group(1)}", name=name, owner=m.group(1))
        elif lead and _norm(name) != _norm(lead["contact_name"]):
            add("signatory_not_authorised", "REVIEW", "signatory_id",
                f"ID belongs to {name}; {lead['contact_role'].lower()} on record is {lead['contact_name']} - "
                "needs an authorisation letter", name=name, owner=lead["contact_name"])
    if lead and lead["has_udyam"] == "Y" and udyam and udyam != lead["udyam_number"]:
        add("udyam_differs_from_lead", "REVIEW", "udyam_certificate",
            f"Lead record has {mask(lead['udyam_number'])}, documents show {mask(udyam)}")
    for i in issues:   # we already know their Udyam number: offer "type it" instead of an upload
        if i.code == "udyam_certificate_missing" and lead and lead["udyam_number"]:
            i.params["has_number"] = True

    # ---- OCR repairs go to the back-office trail
    for d in usable.values():
        for text in d.repairs:
            add("ocr_repair", "NOTE", d.doc_type, text)

    real = [i for i in issues if i.decision != "NOTE"]
    decision = next((s for s in SEVERITY if any(i.decision == s for i in real)), "PASS")
    return KycResult(decision, real, [i for i in issues if i.decision == "NOTE"],
                     gstin, lead["lead_id"] if lead else None)


@lru_cache(maxsize=1)
def _gst_index() -> tuple[str, ...]:
    from .lookups import _gst_registry
    return tuple(_gst_registry())

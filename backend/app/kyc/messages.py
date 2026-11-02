"""What the owner reads about each KYC issue, in their language. Back-office evidence stays in English."""
from __future__ import annotations

from ..i18n import t
from .checks import Issue, KycResult

REGISTRY_MISMATCH = {"gst_legal_name_mismatch", "gst_trade_name_mismatch", "gst_address_mismatch",
                     "gstin_state_mismatch", "udyam_enterprise_name_mismatch", "udyam_city_mismatch",
                     "udyam_state_mismatch", "udyam_belongs_to_other_business"}


def owner_message(issue: Issue, lang: str) -> str:
    doc = t(lang, f"doc.{issue.doc}") if issue.doc else ""
    code = issue.code
    if code == "udyam_certificate_missing" and issue.params.get("has_number"):
        key = "kyc.udyam_certificate_missing.has_number"
    elif code in REGISTRY_MISMATCH:
        key = "kyc.registry_mismatch"
    elif code in ("udyam_format_fail", "udyam_not_in_registry"):
        key = "kyc.udyam_invalid"
    elif t("en", f"kyc.{code}") != f"kyc.{code}":            # a message written for exactly this code
        key = f"kyc.{code}"
    elif code.endswith("_missing"):
        key = "kyc.missing"
    elif code.endswith("_unreadable"):
        key = "kyc.unreadable"
    elif code.endswith("_wrong_document"):
        key = "kyc.wrong_document"
    elif issue.decision == "REVIEW":
        key = "kyc.review"
    else:
        key = f"kyc.decision.{issue.decision}"
    return t(lang, key, doc=doc, **issue.params)


def result_view(res: KycResult, lang: str, back_office: bool = False) -> dict:
    """The owner sees a headline and one plain sentence per issue; the back office also sees codes and evidence."""
    view = {
        "decision": res.decision,
        "headline": t(lang, f"kyc.decision.{res.decision}"),
        "issues": [{"code": i.code, "doc": i.doc, "decision": i.decision, "message": owner_message(i, lang)}
                   for i in res.issues],
    }
    if back_office:
        view["evidence"] = [{"code": i.code, "decision": i.decision, "doc": i.doc, "evidence": i.evidence}
                            for i in res.issues + res.notes]
        view["lead_id"] = res.lead_id
    return view

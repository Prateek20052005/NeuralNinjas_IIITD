"""DigiLocker (demo): fetch the GST and Udyam certificates as issued documents instead of photographing them.

In production the owner signs in to DigiLocker, agrees to share each document with Accel Business, and we receive
the issuer's signed copy (GSTN for the GST registration certificate, the MSME ministry for Udyam). Here the mock
registries stand in for the issuers: the "fetched" certificate carries exactly what the registry holds, so it is never
blurred or mistyped. It still goes through every KYC check (a cancelled GSTIN is still rejected).
Address proof and signatory ID are still photographed (in production: Aadhaar via DigiLocker, and Aadhaar e-sign).
"""
from __future__ import annotations

from .checks import find_lead
from .documents import ParsedDoc
from .lookups import lookup_gstin, lookup_udyam

SOURCE = "Fetched from DigiLocker (demo: mock registry)"
FETCHABLE = ("gst_certificate", "udyam_certificate")


def fetch(doc_type: str, gstin: str | None, udyam_number: str | None = None) -> ParsedDoc | None:
    """The issued certificate for this business, or None if there is none to fetch."""
    if doc_type == "gst_certificate" and gstin:
        r = lookup_gstin(gstin)
        if not r.found:
            return None
        fields = {"gstin": r.gstin, "legal_name": r.legal_name, "trade_name": r.trade_name,
                  "constitution": r.constitution, "address": r.address, "liability_date": r.registration_date,
                  "registration_type": "Regular"}
    elif doc_type == "udyam_certificate":
        number = udyam_number or (find_lead(gstin, None) or {}).get("udyam_number")
        u = lookup_udyam(number) if number else None
        if not u or not u.found:
            return None
        fields = {"udyam_number": u.udyam_number, "enterprise_name": u.enterprise_name,
                  "major_activity": u.major_activity, "city": u.city, "state": u.state,
                  "registration_date": u.registration_date}
    else:
        return None
    return ParsedDoc(doc_type, doc_type, fields, sharpness=1000.0, tilt=0.0, seconds=0.0, repairs=[SOURCE])

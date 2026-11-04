"""KYC checks against the reviewed answer key (tests/kyc_answer_key.csv).

Uses analysis/parsed_docs.json (OCR output saved by scripts/parse_all.py) so these tests run in a
second; test_ocr_reads_a_real_document runs the real OCR on two images.
"""
import csv
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from backend.app.kyc.checks import KycContext, assess
from backend.app.kyc.documents import DOC_TYPES, ParsedDoc, parse_document, read_gstin, read_udyam
from backend.app.kyc.ocr import NotAnImage, read_image

ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 7, 15)
PARSED = json.loads((ROOT / "analysis" / "parsed_docs.json").read_text(encoding="utf-8"))
with open(ROOT / "tests" / "kyc_answer_key.csv", encoding="utf-8") as f:
    KEY = list(csv.DictReader(f))


def docs_for(app: str) -> dict[str, ParsedDoc | None]:
    return {t: ParsedDoc(**PARSED[f"{app}_{t}"]) if f"{app}_{t}" in PARSED else None for t in DOC_TYPES}


@pytest.mark.parametrize("row", KEY, ids=[r["applicant"] for r in KEY])
def test_decision_and_issues_match_answer_key(row):
    res = assess(docs_for(row["applicant"]), KycContext(TODAY))
    assert res.decision == row["expected_decision"]
    assert set(res.codes) == set(filter(None, row["expected_issues"].split(";")))
    assert res.lead_id == row["lead_id"]


def test_missing_udyam_can_be_replaced_by_typing_the_number():
    res = assess(docs_for("K05"), KycContext(TODAY))
    assert res.issues[0].params.get("has_number")                      # we know they have one
    res = assess(docs_for("K05"), KycContext(TODAY, udyam_number="UDYAM-KL-00-5521886"))
    assert res.decision == "PASS"
    res = assess(docs_for("K05"), KycContext(TODAY, udyam_number="UDYAM-KL-00-0000000"))
    assert res.decision == "REJECT" and "udyam_not_in_registry" in res.codes


def test_wrong_document_in_a_slot_asks_for_a_retake():
    docs = docs_for("K03")
    docs["address_proof"] = replace(docs["signatory_id"], doc_type="address_proof")
    res = assess(docs, KycContext(TODAY))
    assert res.decision == "RETAKE" and "address_proof_wrong_document" in res.codes


def test_certificate_for_a_different_gstin_than_the_chat_goes_to_review():
    res = assess(docs_for("K03"), KycContext(TODAY, claimed_gstin="24XORXG9365M1Z3"))
    assert res.decision == "REVIEW" and res.codes == ["gstin_differs_from_application"]


def test_expired_id_and_old_bill_are_retakes_not_rejections():
    res = assess(docs_for("K03"), KycContext(date(2029, 1, 1)))
    assert res.decision == "RETAKE"
    assert {"signatory_id_expired", "address_proof_too_old"} <= set(res.codes)


def test_evidence_never_shows_a_full_identifier():
    for row in KEY:
        res = assess(docs_for(row["applicant"]), KycContext(TODAY))
        for issue in res.issues + res.notes:
            if issue.code != "ocr_repair":     # repair notes show the raw read for the back office trail
                assert "08YKZXS8189L1Z0" not in issue.evidence and "37IHKXV5167L1ZS" not in issue.evidence


@pytest.mark.parametrize("raw,fixed", [("24X0RXG9365M1Z3", "24XORXG9365M1Z3"), ("19E0GXH4115Y1ZL", "19EOGXH4115Y1ZL")])
def test_gstin_ocr_repair(raw, fixed):
    assert read_gstin(raw)[0] == fixed


def test_udyam_ocr_repair():
    assert read_udyam("UDYAM-MH-O0-95I6696")[0] == "UDYAM-MH-00-9516696"


def test_ocr_reads_a_real_document():
    sid = parse_document("signatory_id", read_image((ROOT / "data/kyc_documents/K10_signatory_id.png").read_bytes()))
    assert sid.fields["name"] == "Nisha Arora" and sid.detected_type == "signatory_id"
    blur = parse_document("gst_certificate", read_image((ROOT / "data/kyc_documents/K04_gst_certificate.png").read_bytes()))
    assert blur.sharpness < 100
    with pytest.raises(NotAnImage):
        read_image(b"%PDF-1.4 not an image")


def test_sideways_upside_down_and_shadowed_photos_still_read():
    """Phones send photos turned any way, often with a hand's shadow across them (see scripts/stress_kyc.py)."""
    import cv2
    import numpy as np
    from backend.app.kyc.documents import read_document
    im = cv2.imread(str(ROOT / "data/kyc_documents/K03_gst_certificate.png"))
    shadow = (im * np.linspace(1.0, 0.45, im.shape[1])[None, :, None]).astype(np.uint8)
    for photo in (cv2.rotate(im, cv2.ROTATE_90_CLOCKWISE), cv2.rotate(im, cv2.ROTATE_90_COUNTERCLOCKWISE),
                  cv2.rotate(im, cv2.ROTATE_180), shadow):
        doc = read_document("gst_certificate", cv2.imencode(".png", photo)[1].tobytes())
        assert doc.fields.get("gstin") == "27XUIXG0767D1ZP" and doc.fields["trade_name"] == "Ganesh Woodcraft"


def test_number_printed_but_unread_asks_for_a_retake_not_a_reject():
    """A shadow can hide the Udyam number from the OCR; only an empty box (K01) means a blank certificate."""
    docs = docs_for("K03")
    udyam = docs["udyam_certificate"]
    docs["udyam_certificate"] = replace(udyam, fields={k: v for k, v in udyam.fields.items() if k != "udyam_number"},
                                        unread=["udyam_number"])
    res = assess(docs, KycContext(TODAY))
    assert res.decision == "RETAKE" and res.codes == ["udyam_certificate_unreadable"]


def test_watermark_letters_run_into_an_id_are_dropped_but_extra_digits_are_not():
    assert read_udyam("UDYAM-MH-00-7183141NO")[0] == "UDYAM-MH-00-7183141"
    assert read_udyam("UDYAM-MH-00-71831415")[0] == "UDYAM-MH-00-71831415"       # stays wrong -> format check fails
    assert read_gstin("27XUIXG0767D1ZPNOT")[0] == "27XUIXG0767D1ZP"
    assert read_gstin("27XUIXG0767D1ZQNOT")[0] == "27XUIXG0767D1ZQNOT"           # bad checksum: nothing is trimmed


# ---------- owners without GST (they are only offered products that don't need GST) ----------

def test_owner_without_gst_needs_only_address_proof_and_id():
    docs = {**docs_for("K03"), "gst_certificate": None, "udyam_certificate": None}
    res = assess(docs, KycContext(TODAY, gst_registered=False))
    assert res.decision == "PASS", res.codes
    res = assess(docs, KycContext(TODAY))   # with GST, both certificates are still required
    assert res.decision == "INCOMPLETE"
    assert {"gst_certificate_missing", "udyam_certificate_missing"} <= set(res.codes)


def test_owner_without_gst_but_with_udyam_is_checked_against_udyam():
    docs = {**docs_for("K03"), "gst_certificate": None}
    assert assess(docs, KycContext(TODAY, gst_registered=False)).decision == "PASS"
    docs["udyam_certificate"] = docs_for("K07")["udyam_certificate"]   # someone else's Udyam
    res = assess(docs, KycContext(TODAY, gst_registered=False))
    assert "address_proof_name_mismatch" in res.codes                 # bill is not in the Udyam business's name


def test_owner_without_gst_still_gets_bill_and_id_checks():
    docs = {**docs_for("K11"), "gst_certificate": None, "udyam_certificate": None}   # K11's bill is too old
    assert "address_proof_too_old" in assess(docs, KycContext(TODAY, gst_registered=False)).codes


def test_owner_without_gst_cannot_pass_with_someone_elses_id():
    # the bill is the only proof of the business: an ID for another business must go to a person
    docs = {**docs_for("K03"), "gst_certificate": None, "udyam_certificate": None,
            "signatory_id": docs_for("K07")["signatory_id"]}                    # Ganesh Woodcraft bill, clinic ID
    res = assess(docs, KycContext(TODAY, gst_registered=False))
    assert res.decision == "REVIEW" and "signatory_business_mismatch" in res.codes
    assert any("bill is for" in i.evidence for i in res.issues)

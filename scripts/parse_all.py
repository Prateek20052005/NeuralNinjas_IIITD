"""Read every KYC image with the backend pipeline (OCR + parser) and compare with the reviewed draft fields.

Usage: .venv/Scripts/python scripts/parse_all.py     (about 2 s per image)
Writes analysis/parsed_docs.json so the KYC tests can run without OCR.
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.app.kyc.documents import DOC_TYPES, read_document  # noqa: E402

DRAFT_KEYS = {  # draft script's label text -> backend field name
    "gstin": "gstin", "legal name": "legal_name", "trade name": "trade_name", "address of principal": "address",
    "udyam reg. number": "udyam_number", "enterprise name": "enterprise_name", "city": "city", "state": "state",
    "billed to": "billed_to", "supply address": "supply_address", "bill date": "bill_date",
    "name": "name", "for business": "business", "valid till": "valid_till",
}

draft = json.loads((ROOT / "analysis" / "kyc_findings.json").read_text(encoding="utf-8"))
out, diffs = {}, 0
for img in sorted((ROOT / "data" / "kyc_documents").glob("*.png")):
    app, doc_type = img.stem[:3], img.stem[4:]
    assert doc_type in DOC_TYPES, img.name
    parsed = read_document(doc_type, img.read_bytes())
    out[img.stem] = asdict(parsed)
    old = draft[app]["fields"].get(doc_type, {})
    for k, new_k in DRAFT_KEYS.items():
        if k in old and k != "gstin" and old[k] != parsed.fields.get(new_k):
            diffs += 1
            print(f"{img.stem} {new_k}: draft {old[k]!r} now {parsed.fields.get(new_k)!r}")
    if parsed.wrong_type:
        print(f"{img.stem}: detected as {parsed.detected_type}")
    print(f"{img.stem}: {len(parsed.fields)} fields, sharp {parsed.sharpness}, {parsed.seconds}s {parsed.repairs}")
(ROOT / "analysis" / "parsed_docs.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
print("differences from draft:", diffs)

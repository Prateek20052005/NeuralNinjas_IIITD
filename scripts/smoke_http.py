"""End-to-end check against a running server (local uvicorn or the Docker container), with phone-like photos.

Usage: .venv/Scripts/python scripts/smoke_http.py [base_url]     (default http://localhost:7860)
Uses button taps, so the only AI call is the final explanation (about 1.5K tokens).
"""
import sys
import time
from pathlib import Path

import cv2
import httpx
import numpy as np

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:7860") + "/api"
DOCS = Path(__file__).resolve().parent.parent / "data" / "kyc_documents"
TAPS = [("gstin", "27XUIXG0767D1ZP"), ("gst_confirm", "yes"), ("segment", "mfg"), ("employees", "12"), ("sites", "1"),
        ("need:machines", "4"), ("need:vehicles", "0"), ("need:firewall", "yes")]


def photo(doc_type, how):
    im = cv2.imread(str(DOCS / f"K03_{doc_type}.png"))
    if how == "sideways":
        im = cv2.rotate(im, cv2.ROTATE_90_CLOCKWISE)
    elif how == "shadow":
        im = (im * np.linspace(1.0, 0.45, im.shape[1])[None, :, None]).astype(np.uint8)
    return cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


def main():
    c = httpx.Client(timeout=60)
    out = c.post(f"{BASE}/applications", json={"language": "en"}).json()
    app_id = out["id"]
    for slot, value in TAPS:
        out = c.post(f"{BASE}/applications/{app_id}/message", json={"slot": slot, "value": value}).json()
    rec = out["recommendation"]
    print("bundle:", {x["id"]: x["quantity"] for x in rec["core"]}, "| monthly incl. GST:", rec["quote"]["monthly_with_gst"])
    print("summary:", (rec.get("summary") or "")[:120])
    for extra in rec["addons"]:
        q = c.post(f"{BASE}/applications/{app_id}/addons", json={"product_id": extra["id"], "on": True}).json()["quote"]
        line = next(x for x in q["lines"] if x["product_id"] == extra["id"])
        assert line["quantity"] == extra["quantity"], (extra, line)
    print("extras switched on at suggested quantities:", {x["id"]: x["quantity"] for x in rec["addons"]})
    c.post(f"{BASE}/applications/{app_id}/accept")
    c.post(f"{BASE}/applications/{app_id}/consent", json={"purposes": ["kyc"]})
    for doc_type, how in [("gst_certificate", "sideways"), ("udyam_certificate", "shadow"),
                          ("address_proof", "upright"), ("signatory_id", "sideways")]:
        t0 = time.time()
        r = c.post(f"{BASE}/applications/{app_id}/documents/{doc_type}",
                   files={"file": ("p.jpg", photo(doc_type, how), "image/jpeg")}).json()
        print(f"{doc_type:<18} {how:<9} ok={r['ok']} {time.time() - t0:.1f}s {r['message']}")
    res = c.post(f"{BASE}/applications/{app_id}/kyc").json()
    print("KYC decision:", res["decision"])
    steps = [s["step"] for s in c.get(f"{BASE}/applications/{app_id}").json()["timeline"]]
    print("timeline:", " > ".join(steps))
    assert c.delete(f"{BASE}/applications/{app_id}").json()["deleted"]
    assert c.get(f"{BASE}/applications/{app_id}").status_code == 404
    print("deleted: ok")


if __name__ == "__main__":
    main()

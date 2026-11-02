"""First-pass KYC findings for K01-K12: parse OCR output into fields, then check them
against the mock registries, the leads file and each other. Output: analysis/kyc_findings.json

This is a draft answer key; every finding is reviewed by eye before it goes into tests/.
Usage: .venv/Scripts/python scripts/kyc_findings.py
"""
import json
import re
from datetime import date
from pathlib import Path

import cv2
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TODAY = date(2026, 7, 15)
DOC_TYPES = ["gst_certificate", "udyam_certificate", "address_proof", "signatory_id"]

GST_STATE_CODES = {"03": "Punjab", "07": "Delhi", "08": "Rajasthan", "19": "West Bengal", "24": "Gujarat",
                   "27": "Maharashtra", "32": "Kerala", "37": "Andhra Pradesh"}
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TO_LETTER = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"}
TO_DIGIT = {v: k for k, v in TO_LETTER.items()}
# Position kinds in a GSTIN: d = digit, L = letter, a = either
GSTIN_PATTERN = "ddLLLLLddddLaZa"


def gstin_checksum_ok(g):
    total = 0
    for i, ch in enumerate(g[:14]):
        v = CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return CHARS[(36 - total % 36) % 36] == g[14]


def fix_gstin(raw):
    """Repair common OCR swaps (0/O, 1/I, 5/S...) using the fixed GSTIN layout."""
    g = re.sub(r"[^0-9A-Z]", "", raw.upper())
    if len(g) != 15:
        return g
    out = []
    for ch, kind in zip(g, GSTIN_PATTERN):
        if kind == "L":
            ch = TO_LETTER.get(ch, ch)
        elif kind == "d":
            ch = TO_DIGIT.get(ch, ch)
        out.append(ch)
    return "".join(out)


def parse_fields(lines):
    """Pair each label (left column) with the value printed on the same row (right column)."""
    labels = [l for l in lines if l["x"] < 450]
    values = [l for l in lines if l["x"] >= 450]
    fields, last = {}, None
    for v in sorted(values, key=lambda l: l["y"]):
        lab = min(labels, key=lambda l: abs(l["y"] - v["y"]), default=None)
        key = lab["text"].strip().rstrip(".").lower() if lab and abs(lab["y"] - v["y"]) < 30 else None
        if key in (None, "place of business") and last:
            # no label on this row (or the 2nd half of the GST address label): wrapped value
            fields[last] += v["text"]
            continue
        if key:
            fields[key] = v["text"]
            last = key
    return fields


def parse_id_card(lines):
    """Signatory ID: label above value, both in the right-hand column."""
    rows = sorted(lines, key=lambda l: l["y"])
    names = ["Name", "Designation", "For business", "ID no.", "Valid till"]
    fields = {}
    for i, l in enumerate(rows):
        if l["text"] in names and i + 1 < len(rows):
            fields[l["text"].rstrip(".").lower()] = rows[i + 1]["text"]
    if "valid till" not in fields:  # label can be lost; take the last date on the card
        dates = [l["text"] for l in rows if re.fullmatch(r"\d{4}-\d{2}-\d{2}", l["text"])]
        if dates:
            fields["valid till"] = dates[-1]
    return fields


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def sharpness(path):
    return round(float(cv2.Laplacian(cv2.imread(str(path), cv2.IMREAD_GRAYSCALE), cv2.CV_64F).var()), 1)


def main():
    ocr = json.loads((ROOT / "analysis" / "ocr_raw.json").read_text(encoding="utf-8"))
    gst_reg = pd.read_csv(DATA / "mock_gstin_registry.csv").set_index("gstin")
    udyam_reg = pd.read_csv(DATA / "mock_udyam_registry.csv").set_index("udyam_number")
    leads = pd.read_csv(DATA / "smb_leads.csv")

    report = {}
    for n in range(1, 13):
        app = f"K{n:02d}"
        docs, issues = {}, []
        for t in DOC_TYPES:
            name = f"{app}_{t}.png"
            if name not in ocr:
                issues.append(f"MISSING DOCUMENT: {t}")
                continue
            lines = ocr[name]["lines"]
            f = parse_id_card(lines) if t == "signatory_id" else parse_fields(lines)
            f["_sharpness"] = sharpness(DATA / "kyc_documents" / name)
            f["_lines"] = len(lines)
            docs[t] = f
            if f["_sharpness"] < 100:
                issues.append(f"UNREADABLE/BLURRED: {t} (sharpness {f['_sharpness']})")

        gst = docs.get("gst_certificate", {})
        udy = docs.get("udyam_certificate", {})
        bill = docs.get("address_proof", {})
        sid = docs.get("signatory_id", {})

        # --- GST certificate vs registry
        g_raw = gst.get("gstin", "")
        g = fix_gstin(g_raw)
        if len(g) == 15 and not gstin_checksum_ok(g):
            # 0/O and 1/I look identical in this font; try the other reading in "either" positions
            for i, kind in enumerate(GSTIN_PATTERN):
                swap = {"0": "O", "O": "0", "1": "I", "I": "1"}.get(g[i])
                if kind == "a" and swap and gstin_checksum_ok(g[:i] + swap + g[i + 1:]):
                    g = g[:i] + swap + g[i + 1:]
                    break
        reg = None
        if g:
            if g != re.sub(r"[^0-9A-Z]", "", g_raw.upper()):
                issues.append(f"note: OCR GSTIN '{g_raw}' repaired to '{g}'")
            if len(g) != 15 or not gstin_checksum_ok(g):
                near = [x for x in gst_reg.index if sum(a != b for a, b in zip(x, g)) <= 2]
                issues.append(f"GSTIN FORMAT/CHECKSUM FAIL: {g}" + (f" (closest registry GSTIN: {near[0]})" if near else ""))
            elif g not in gst_reg.index:
                issues.append(f"GSTIN NOT IN REGISTRY: {g}")
            else:
                reg = gst_reg.loc[g]
                if reg.status != "Active":
                    issues.append(f"GSTIN STATUS {reg.status.upper()}")
                if norm(gst.get("legal name")) != norm(reg.legal_name):
                    issues.append(f"GST LEGAL NAME MISMATCH: doc '{gst.get('legal name')}' vs registry '{reg.legal_name}'")
                if norm(gst.get("trade name")) != norm(reg.trade_name):
                    issues.append(f"GST TRADE NAME MISMATCH: doc '{gst.get('trade name')}' vs registry '{reg.trade_name}'")
                if norm(gst.get("address of principal")) != norm(reg.principal_place_of_business):
                    issues.append(f"GST ADDRESS MISMATCH: doc '{gst.get('address of principal')}' vs registry '{reg.principal_place_of_business}'")
                if norm(gst.get("date of liability")) != norm(reg.registration_date):
                    issues.append(f"GST DATE MISMATCH: doc '{gst.get('date of liability')}' vs registry '{reg.registration_date}'")
                if GST_STATE_CODES.get(g[:2]) and GST_STATE_CODES[g[:2]] != reg.state:
                    issues.append(f"GSTIN STATE CODE {g[:2]} does not match state {reg.state}")
        elif "gst_certificate" in docs:
            issues.append("GSTIN NOT READ from certificate")

        # --- Udyam certificate vs registry
        if "udyam_certificate" in docs:
            u = udy.get("udyam reg. number") or udy.get("udyam reg", "")
            if not u:
                issues.append("UDYAM NUMBER BLANK on certificate")
            elif not re.fullmatch(r"UDYAM-[A-Z]{2}-\d{2}-\d{7}", u):
                issues.append(f"UDYAM FORMAT FAIL: {u}")
            elif u not in udyam_reg.index:
                issues.append(f"UDYAM NOT IN REGISTRY: {u}")
            else:
                ur = udyam_reg.loc[u]
                for doc_key, reg_key in [("enterprise name", "enterprise_name"), ("city", "city"), ("state", "state")]:
                    if norm(udy.get(doc_key)) != norm(ur[reg_key]):
                        issues.append(f"UDYAM {doc_key.upper()} MISMATCH: doc '{udy.get(doc_key)}' vs registry '{ur[reg_key]}'")
                # Activity and date differ on nearly every specimen certificate (generator noise), so note only
                for doc_key, reg_key in [("major activity", "major_activity"), ("date of registration", "date_of_registration")]:
                    if norm(udy.get(doc_key)) != norm(ur[reg_key]):
                        issues.append(f"note: udyam {doc_key} '{udy.get(doc_key)}' vs registry '{ur[reg_key]}'")
            trade = reg.trade_name if reg is not None else gst.get("trade name")
            if trade and norm(udy.get("enterprise name")) != norm(trade):
                issues.append(f"UDYAM NAME vs GST TRADE NAME: '{udy.get('enterprise name')}' vs '{trade}'")

        # --- Address proof
        if bill:
            trade = reg.trade_name if reg is not None else gst.get("trade name")
            if trade and norm(bill.get("billed to")) != norm(trade):
                issues.append(f"BILL NAME MISMATCH: '{bill.get('billed to')}' vs '{trade}'")
            addr = reg.principal_place_of_business if reg is not None else gst.get("address of principal")
            if addr and norm(bill.get("supply address")) != norm(addr):
                issues.append(f"BILL ADDRESS MISMATCH: '{bill.get('supply address')}' vs '{addr}'")
            try:
                age = (TODAY - date.fromisoformat(bill.get("bill date", ""))).days
                if age > 90:
                    issues.append(f"ADDRESS PROOF TOO OLD: {age} days")
                elif age < 0:
                    issues.append(f"ADDRESS PROOF DATED IN FUTURE: {bill.get('bill date')}")
            except ValueError:
                issues.append("BILL DATE NOT READ")

        # --- Signatory ID
        if sid:
            trade = reg.trade_name if reg is not None else gst.get("trade name")
            if trade and norm(sid.get("for business")) != norm(trade):
                issues.append(f"ID BUSINESS MISMATCH: '{sid.get('for business')}' vs '{trade}'")
            legal = reg.legal_name if reg is not None else gst.get("legal name", "")
            m = re.match(r"(.+?) \(Prop\.", str(legal))
            if m and norm(sid.get("name")) != norm(m.group(1)):
                issues.append(f"SIGNATORY NOT PROPRIETOR: ID '{sid.get('name')}' vs GST proprietor '{m.group(1)}'")
            try:
                if date.fromisoformat(sid.get("valid till", "")) < TODAY:
                    issues.append(f"SIGNATORY ID EXPIRED: {sid.get('valid till')}")
            except ValueError:
                issues.append("ID VALIDITY NOT READ")

        # --- Link to leads file
        lead = leads[leads.gstin == g] if g else leads.iloc[0:0]
        u_num = udy.get("udyam reg. number") or udy.get("udyam reg")
        if not len(lead) and u_num:  # GSTIN unreadable: fall back to the Udyam number
            lead = leads[leads.udyam_number == u_num]
        lead_info = None
        if len(lead):
            r = lead.iloc[0]
            lead_info = {k: (None if pd.isna(r[k]) else str(r[k])) for k in
                         ["lead_id", "business_name", "city", "has_udyam", "udyam_number", "contact_name",
                          "contact_role", "stage_reached", "drop_reason"]}
            if r.has_udyam == "Y" and u_num and u_num != r.udyam_number:
                issues.append(f"UDYAM DIFFERS FROM LEAD RECORD: lead has {r.udyam_number}")
            if sid and norm(r.contact_name) != norm(sid.get("name")):
                issues.append(f"SIGNATORY NOT THE CONTACT ON RECORD: ID '{sid.get('name')}' vs lead contact "
                              f"'{r.contact_name}' ({r.contact_role})")

        report[app] = {"gstin": g, "lead": lead_info, "issues": issues,
                       "fields": {t: {k: v for k, v in f.items()} for t, f in docs.items()}}

    out = ROOT / "analysis" / "kyc_findings.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    for app, r in report.items():
        print(f"\n{app}  GSTIN={r['gstin']}  lead={r['lead']['lead_id'] if r['lead'] else '-'}")
        for i in r["issues"] or ["no issues found"]:
            print("   -", i)


if __name__ == "__main__":
    main()

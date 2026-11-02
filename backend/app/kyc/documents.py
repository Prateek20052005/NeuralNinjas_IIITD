"""Turn OCR lines from one KYC document into named fields.

Four document types. Certificates and the bill are two-column tables (label left, value right, long
values wrap onto the next row). The signatory ID prints each label above its value. Rows are matched by
height, not fixed pixel positions, so a photo of any size works.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .lookups import CHARS, gstin_checksum_ok
from .ocr import BLUR_LIMIT, OcrLine, OcrResult, ink, read_image, read_region

DOC_TYPES = ("gst_certificate", "udyam_certificate", "address_proof", "signatory_id")

# printed label -> field name, per document type
LABELS = {
    "gst_certificate": {"gstin": "gstin", "legal name": "legal_name", "trade name": "trade_name",
                        "constitution": "constitution", "address of principal": "address",
                        "date of liability": "liability_date", "type of registration": "registration_type"},
    "udyam_certificate": {"udyam reg number": "udyam_number", "enterprise name": "enterprise_name",
                          "major activity": "major_activity", "city": "city", "state": "state",
                          "date of registration": "registration_date"},
    "address_proof": {"consumer no": "consumer_no", "billed to": "billed_to", "supply address": "supply_address",
                      "bill date": "bill_date", "units consumed": "units", "amount due": "amount"},
    "signatory_id": {"name": "name", "designation": "designation", "for business": "business",
                     "id no": "id_no", "valid till": "valid_till"},
}
CONTINUATION_LABELS = {"place of business"}   # 2nd line of the GST address label: its value continues the address
TITLE_WORDS = {"gst_certificate": "gst registration", "udyam_certificate": "udyam registration",
               "address_proof": "electricity bill", "signatory_id": "signatory"}

TO_LETTER = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"}
TO_DIGIT = {v: k for k, v in TO_LETTER.items()}
GSTIN_LAYOUT = "ddLLLLLddddLaZa"      # d = digit, L = letter, a = either


@dataclass
class ParsedDoc:
    doc_type: str                     # slot the owner uploaded into
    detected_type: str | None         # what the document looks like
    fields: dict[str, str]
    sharpness: float
    tilt: float
    seconds: float
    repairs: list[str] = field(default_factory=list)   # e.g. OCR 0->O fixes, for the back-office trail
    unread: list[str] = field(default_factory=list)    # printed on the document but could not be read

    @property
    def blurred(self) -> bool:
        return self.sharpness < BLUR_LIMIT

    @property
    def wrong_type(self) -> bool:
        return self.detected_type is not None and self.detected_type != self.doc_type


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _label_of(text: str, labels: dict[str, str]) -> str | None:
    n = _norm(text)
    for printed in list(labels) + list(CONTINUATION_LABELS):
        if n == _norm(printed) or (len(n) > 3 and n.startswith(_norm(printed))):
            return printed
    return None


def detect_type(lines: list[OcrLine]) -> str | None:
    """Which document this is, from its title or (if the title is unreadable) the labels it carries."""
    text = " ".join(line.text.lower() for line in lines)
    for t, words in TITLE_WORDS.items():
        if words in text:
            return t
    scores = {t: sum(1 for line in lines if _label_of(line.text, LABELS[t])) for t in DOC_TYPES}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 3 else None


def _parse_table(lines: list[OcrLine], labels: dict[str, str], gaps: dict | None = None) -> dict[str, str]:
    """Label column on the left, values on the right. Labels with no value are put in `gaps` as
    field -> (x0, y0, x1, y1), the box where the value should be, so it can be checked for ink."""
    tol = 0.8 * (sorted(line.h for line in lines)[len(lines) // 2] if lines else 30)
    label_lines = [(line, _label_of(line.text, labels)) for line in lines]
    label_rows = [(line, lab) for line, lab in label_lines if lab]
    others = [line for line, lab in label_lines if not lab]
    if not label_rows:
        return {}
    # value column = typical x of text that shares a row with a label (ignores stray watermark letters)
    on_rows = [o for o in others if any(abs(o.y - lab.y) < tol and o.x > lab.x for lab, _ in label_rows)]
    if not on_rows:
        return {}
    col_x = sorted(o.x for o in on_rows)[len(on_rows) // 2]
    values = sorted((o for o in others if abs(o.x - col_x) < 4 * tol), key=lambda o: o.y)

    fields, last, last_y = {}, None, None
    for v in values:
        row = [(lab, name) for lab, name in label_rows if abs(lab.y - v.y) < tol]
        name = min(row, key=lambda r: abs(r[0].y - v.y))[1] if row else None
        if name in labels and labels[name] not in fields:
            fields[labels[name]] = v.text
            last, last_y = labels[name], v.y
        elif last and (name in CONTINUATION_LABELS or (name is None and v.y - last_y < 3 * tol)):
            fields[last] += v.text  # wrapped value (OCR cuts mid-word, e.g. "Maharashtr" + "a - 411231")
            last_y = v.y
    if gaps is not None:
        for lab, name in label_rows:
            if name in labels and labels[name] not in fields:
                gaps[labels[name]] = (round(col_x - tol), round(lab.y - 0.4 * lab.h),
                                      round(col_x + 22 * lab.h), round(lab.y + 1.4 * lab.h))
    return fields


def _parse_card(lines: list[OcrLine], labels: dict[str, str]) -> dict[str, str]:
    rows = sorted(lines, key=lambda line: line.y)
    fields = {}
    for i, line in enumerate(rows):
        lab = _label_of(line.text, labels)
        if lab not in labels or labels[lab] in fields:
            continue
        below = [r for r in rows[i + 1:] if r.y - line.y < 3 * line.h and abs(r.x - line.x) < 4 * line.h
                 and not _label_of(r.text, labels)]
        if below:
            fields[labels[lab]] = below[0].text
    if "valid_till" not in fields:  # the label itself can be lost; the last date on the card is the expiry
        dates = [line.text for line in rows if parse_date(line.text)]
        if dates:
            fields["valid_till"] = dates[-1]
    return fields


def read_gstin(raw: str) -> tuple[str, list[str]]:
    """Repair common OCR swaps (0/O, 1/I, 5/S, 8/B, 2/Z) using the fixed GSTIN layout and its checksum."""
    g = re.sub(r"[^0-9A-Z]", "", (raw or "").upper())
    notes = []
    if len(g) > 15 and g[15:].isalpha() and gstin_checksum_ok(g[:15]):
        notes.append(f"dropped '{g[15:]}' read after the GSTIN (watermark letters)")
        g = g[:15]
    if len(g) != 15:
        return g, notes
    fixed = "".join(TO_LETTER.get(c, c) if k == "L" else TO_DIGIT.get(c, c) if k == "d" else c
                    for c, k in zip(g, GSTIN_LAYOUT))
    if all(c in CHARS for c in fixed) and not gstin_checksum_ok(fixed):
        # in "either" positions 0/O and 1/I look the same in this font: try the other reading
        for i, kind in enumerate(GSTIN_LAYOUT):
            swap = {"0": "O", "O": "0", "1": "I", "I": "1"}.get(fixed[i])
            if kind == "a" and swap and gstin_checksum_ok(fixed[:i] + swap + fixed[i + 1:]):
                fixed = fixed[:i] + swap + fixed[i + 1:]
                break
    return fixed, notes + ([f"GSTIN read as {g}, corrected to {fixed}"] if fixed != g else [])


def read_udyam(raw: str) -> tuple[str, list[str]]:
    """UDYAM-XX-00-0000000: letters for the state, digits elsewhere."""
    s = re.sub(r"\s", "", (raw or "").upper())
    # trailing letters are watermark text run into the number; trailing digits would be a wrong number, so they stay
    m = re.fullmatch(r"UDYAM-?([A-Z0-9]{2})-?([A-Z0-9]{2})-?([A-Z0-9]{7})([A-Z]{0,6})", s)
    if not m:
        return s, []
    st, mid, num, junk = m.groups()
    fixed = "UDYAM-{}-{}-{}".format("".join(TO_LETTER.get(c, c) for c in st),
                                    "".join(TO_DIGIT.get(c, c) for c in mid), "".join(TO_DIGIT.get(c, c) for c in num))
    return fixed, ([f"Udyam number read as {s}, corrected to {fixed}"] if fixed != s[:len(s) - len(junk)] else []) \
        + ([f"dropped '{junk}' read after the Udyam number (watermark letters)"] if junk else [])


def parse_date(text: str) -> date | None:
    s = (text or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{2})[/.-](\d{2})[/.-](\d{4})", s)   # Indian style dd/mm/yyyy
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def read_document(doc_type: str, data: bytes) -> ParsedDoc:
    """OCR + parse a photo, turning it the right way up first if it was taken sideways or upside down.
    An upright photo is read once; a turned one two or three times (about 2 s each)."""
    first = read_image(data)
    sideways = first.tall_text > 0.5
    best, seconds = _parse_upright(doc_type, first), first.seconds
    for turn in ([1, 3] if sideways else [2]):   # sideways: a quarter turn either way; else maybe upside down
        if not _weak(best):
            break
        ocr = read_image(data, turned=turn)
        alt, seconds = _parse_upright(doc_type, ocr), seconds + ocr.seconds
        if len(alt.fields) > len(best.fields) or not _weak(alt):
            best = alt
    best.seconds = round(seconds, 2)
    return best


def _parse_upright(doc_type: str, ocr: OcrResult) -> ParsedDoc:
    doc = parse_document(doc_type, ocr)
    if ocr.tall_text > 0.5 or _title_at_bottom(ocr.lines):
        doc.fields = {}   # read sideways or upside down: labels got matched to the wrong values, so none count
    return doc


def _title_at_bottom(lines: list[OcrLine]) -> bool:
    """Every document has its title near the top; found in the lower half means the photo is upside down."""
    ys = [line.y for line in lines]
    titles = [line.y for line in lines if any(w in line.text.lower() for w in TITLE_WORDS.values())]
    return bool(titles) and min(titles) > (min(ys) + max(ys)) / 2


def _weak(doc: ParsedDoc) -> bool:
    """Fewer than half the expected fields, or a 'field' that is really a whole page of run-together text."""
    return len(doc.fields) * 2 < len(LABELS[doc.doc_type]) or any(len(v) > 120 for v in doc.fields.values())


def parse_document(doc_type: str, ocr: OcrResult) -> ParsedDoc:
    detected = detect_type(ocr.lines)
    labels, gaps = LABELS[doc_type], {}
    fields = _parse_card(ocr.lines, labels) if doc_type == "signatory_id" else _parse_table(ocr.lines, labels, gaps)
    unread = []
    for name, box in gaps.items():   # a label with nothing next to it: blank on the paper, or missed by the OCR?
        if ocr.image is None or ink(ocr.image, *box) < 0.01:
            continue                 # really blank (K01's empty Udyam number): the checks decide what that means
        text = read_region(ocr.image, *box)
        if text:
            fields[name] = text
        else:
            unread.append(name)
    repairs = [f"photo straightened by {abs(ocr.tilt)} degrees"] if ocr.tilt else []
    if ocr.turned:
        repairs.append(f"photo turned {ocr.turned * 90} degrees to read it")
    if "gstin" in fields:
        fields["gstin"], notes = read_gstin(fields["gstin"])
        repairs += notes
    if "udyam_number" in fields:
        fields["udyam_number"], notes = read_udyam(fields["udyam_number"])
        repairs += notes
    return ParsedDoc(doc_type, detected, fields, ocr.sharpness, ocr.tilt, ocr.seconds, repairs, unread)

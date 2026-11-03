"""Mock GSTIN and Udyam lookups, backed by the registry CSVs, plus ID masking for logs and screens.

GSTIN layout: 2-digit state code, 10-character PAN, entity number, 'Z', checksum.
In this dataset the PAN's 4th character is always 'X' (not a real entity type), which we accept.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache

from ..catalogue import DATA_DIR
from ..i18n import INDIC_DIGITS

CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")


def gstin_checksum_ok(g: str) -> bool:
    total = 0
    for i, ch in enumerate(g[:14]):
        v = CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return CHARS[(36 - total % 36) % 36] == g[14]


def clean_id(raw: str) -> str:
    """Uppercase and drop spaces; drop dashes too, except in Udyam numbers where they are part of the format."""
    s = (raw or "").strip().upper()
    return re.sub(r"\s", "", s) if s.startswith("UDYAM") else re.sub(r"[\s-]", "", s)


def mask(value: str | None) -> str:
    """'37IHKXV5167L1ZS' -> '37IHK******L1ZS'. Used everywhere an ID is logged or shown back."""
    if not value:
        return ""
    v = str(value)
    if len(v) <= 6:
        return "*" * len(v)
    keep = 5 if len(v) > 12 else 2
    return v[:keep] + "*" * (len(v) - keep - 4) + v[-4:]


@dataclass
class GstinResult:
    gstin: str
    format_ok: bool
    found: bool
    status: str | None = None          # Active / Cancelled / Suspended
    legal_name: str | None = None
    trade_name: str | None = None
    constitution: str | None = None
    address: str | None = None
    state: str | None = None
    registration_date: str | None = None

    @property
    def active(self) -> bool:
        return self.found and self.status == "Active"

    @property
    def business_status(self) -> str:
        """Value for Business.gstin_status."""
        return "active" if self.active else ("inactive" if self.found else "none")


@dataclass
class UdyamResult:
    udyam_number: str
    format_ok: bool
    found: bool
    enterprise_name: str | None = None
    enterprise_type: str | None = None
    major_activity: str | None = None
    nic_description: str | None = None
    city: str | None = None
    state: str | None = None
    registration_date: str | None = None


@lru_cache(maxsize=1)
def _gst_registry() -> dict[str, dict]:
    with open(DATA_DIR / "mock_gstin_registry.csv", encoding="utf-8") as f:
        return {r["gstin"]: r for r in csv.DictReader(f)}


@lru_cache(maxsize=1)
def _udyam_registry() -> dict[str, dict]:
    with open(DATA_DIR / "mock_udyam_registry.csv", encoding="utf-8") as f:
        return {r["udyam_number"]: r for r in csv.DictReader(f)}


def lookup_gstin(raw: str) -> GstinResult:
    g = clean_id(raw)
    ok = bool(GSTIN_RE.match(g)) and gstin_checksum_ok(g)
    r = _gst_registry().get(g) if ok else None
    if not r:
        return GstinResult(g, ok, False)
    return GstinResult(g, True, True, r["status"], r["legal_name"], r["trade_name"], r["constitution"],
                       r["principal_place_of_business"], r["state"], r["registration_date"])


def lookup_udyam(raw: str) -> UdyamResult:
    u = clean_id(raw)
    ok = bool(UDYAM_RE.match(u))
    r = _udyam_registry().get(u) if ok else None
    if not r:
        return UdyamResult(u, ok, False)
    return UdyamResult(u, True, True, r["enterprise_name"], r["enterprise_type"], r["major_activity"],
                       r["nic_description"], r["city"], r["state"], r["date_of_registration"])


def find_gstin_in_text(text: str) -> str | None:
    """Pull a GSTIN-looking token out of a chat message."""
    m = re.search(r"\b\d{2}[A-Z0-9]{10}[0-9A-Z]Z[0-9A-Z]\b", (text or "").upper())
    return m.group(0) if m else None


_DIGIT = f"[0-9{INDIC_DIGITS}]"   # digits typed in any supported script
ID_PATTERNS = [
    re.compile(r"\bUDYAM[\s-]*[A-Z]{2}[\s-]*\d{2}[\s-]*\d{7}\b", re.I),     # Udyam number
    re.compile(r"\b\d{2}[A-Z0-9]{10}[0-9A-Z]Z[0-9A-Z]\b", re.I),            # GSTIN (also mistyped ones)
    re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I),                            # PAN
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),                                 # email
    re.compile(rf"(?:\+?{_DIGIT}{{1,3}}[\s-]?)?(?:{_DIGIT}[\s-]?){{7,}}{_DIGIT}"),  # phone, Aadhaar, account: 8+ digits
]


def redact_ids(text: str, names: tuple[str, ...] = ()) -> str:
    """Remove ID numbers (and the given names) from free text before it leaves our server.
    Small numbers like '12 staff' are kept: only runs of 8+ digits are removed."""
    out = text or ""
    for pat in ID_PATTERNS:
        out = pat.sub("[removed]", out)
    for name in names:
        if name and len(name) > 2:
            out = re.sub(re.escape(name), "[business]", out, flags=re.I)
    return out

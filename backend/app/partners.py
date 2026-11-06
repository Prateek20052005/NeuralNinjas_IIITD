"""Channel partners and the field force: the app adds to them instead of competing with them.

- A partner shares a referral link (/?ref=RAJ01). Applications from it carry the partner's code, so the partner keeps
  their commission even though the owner buys in the app. With &assisted=1 the partner is sitting with the owner and
  the app does the paperwork ("assisted mode"); the owner still verifies their own mobile and gives their own consent.
- Back-office roles: staff (BACKOFFICE_KEY) see everything they need, with identifiers masked. A partner (its own key
  in PARTNER_KEYS, "RAJ01=key;SHAH02=key") sees only the applications it referred, and never documents, KYC evidence,
  GST numbers or phone numbers.
"""
from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Viewer:
    role: str                 # "staff" | "partner"
    partner: str | None = None

    @property
    def name(self) -> str:
        return "staff" if self.role == "staff" else f"partner {self.partner}"


@lru_cache(maxsize=1)
def partners() -> dict[str, dict]:
    with open(Path(__file__).with_name("partners.json"), encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def partner_code(raw: str | None) -> str | None:
    """A referral code from a link, if it is one of ours (anything else is ignored, not an error)."""
    code = (raw or "").strip().upper()
    return code if code in partners() else None


def partner_view(code: str | None) -> dict | None:
    return {"code": code, **partners()[code]} if code in partners() else None


def _partner_keys() -> dict[str, str]:
    out = {}
    for pair in os.getenv("PARTNER_KEYS", "").replace(",", ";").split(";"):
        code, _, key = pair.partition("=")
        if code.strip().upper() in partners() and key.strip():
            out[code.strip().upper()] = key.strip()
    return out


def viewer_for(key: str | None) -> Viewer | None:
    """Who is using the back office, from the key they typed; None = no access."""
    if not key:
        return None
    staff = os.getenv("BACKOFFICE_KEY")
    if staff and hmac.compare_digest(key, staff):
        return Viewer("staff")
    for code, partner_key in _partner_keys().items():
        if hmac.compare_digest(key, partner_key):
            return Viewer("partner", code)
    return None

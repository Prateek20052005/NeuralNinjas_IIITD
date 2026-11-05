"""Is this business already an Accel customer? (The welcome offer is for first-time customers only.)

Our records are the CRM leads file: a GSTIN whose lead already uses Accel (current_provider "Accel" or
"Accel (mobile only)") or whose lead was activated counts as an existing customer. Owners without a GSTIN can't be
matched, so the chat asks them one yes/no question instead.
"""
from __future__ import annotations

import csv
from functools import lru_cache

from .catalogue import DATA_DIR


@lru_cache(maxsize=1)
def _existing_gstins() -> frozenset[str]:
    with open(DATA_DIR / "smb_leads.csv", encoding="utf-8") as f:
        return frozenset(r["gstin"] for r in csv.DictReader(f)
                         if r["gstin"] and (r["current_provider"].startswith("Accel") or r["outcome"] == "Activated"))


def is_existing_customer(gstin: str | None) -> bool:
    return bool(gstin) and gstin in _existing_gstins()

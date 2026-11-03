"""One owner's application from first chat message to KYC decision, kept in memory.

Privacy (DPDP Act 2023) by design:
- Document photos are read in memory and never written to disk; only the parsed fields are kept.
- KYC needs recorded consent first, for named purposes, with the consent text version and time.
- Applications are deleted after RETENTION_HOURS without activity, or at once when the owner asks.
- Logs and screens only ever show masked identifiers.
A real deployment would move this to an encrypted database; the rules stay the same.
"""
from __future__ import annotations

import logging
import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .advisor.engine import Session
from .kyc.checks import KycResult
from .kyc.documents import ParsedDoc
from .kyc.lookups import mask

log = logging.getLogger("store")
CONSENT_VERSION = "2026-07-v1"
CONSENT_PURPOSES = ("kyc", "contact")
MASKED_FIELDS = {"gstin", "udyam_number", "consumer_no", "id_no"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Consent:
    purposes: list[str]
    language: str
    version: str = CONSENT_VERSION
    given_at: str = field(default_factory=lambda: _now().isoformat(timespec="seconds"))


@dataclass
class Application:
    id: str
    session: Session
    items: dict[str, int] = field(default_factory=dict)       # bundle after the owner's add-on switches
    tier: str = "recommended"                                   # basic / recommended / full / custom
    contract_months: int | None = None                          # owner's choice; None = bundle minimum
    setup_months: int = 1                                       # setup fee paid at once (1) or spread
    discount_pct: float = 0.0                                   # negotiated on the plan screen (negotiate.py)
    price_asks: int = 0                                         # times the owner asked for a lower price
    callback: dict | None = None                                # salesperson call: phone kept only for that call
    accepted: bool = False
    consent: Consent | None = None
    docs: dict[str, ParsedDoc] = field(default_factory=dict)
    udyam_number: str | None = None
    kyc: KycResult | None = None
    timeline: list[dict] = field(default_factory=list)        # tracker steps for the owner
    last_seen: datetime = field(default_factory=_now)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @property
    def language(self) -> str:
        return self.session.profile.language

    def mark(self, step: str, **info) -> None:
        self.timeline.append({"step": step, "at": _now().isoformat(timespec="seconds"), **info})
        log.info("app=%s step=%s %s", self.id[:6], step, {k: mask(str(v)) if k in MASKED_FIELDS else v
                                                         for k, v in info.items()})


def masked_fields(doc: ParsedDoc) -> dict[str, str]:
    return {k: mask(v) if k in MASKED_FIELDS else v for k, v in doc.fields.items()}


class Store:
    def __init__(self, retention_hours: float | None = None):
        hours = retention_hours if retention_hours is not None else float(os.getenv("RETENTION_HOURS", "72"))
        self.retention = timedelta(hours=hours)
        self._apps: dict[str, Application] = {}
        self._lock = threading.Lock()

    def create(self, session: Session) -> Application:
        app = Application(secrets.token_urlsafe(16), session)   # unguessable id: it is the owner's only key
        with self._lock:
            self._apps[app.id] = app
        return app

    def get(self, app_id: str) -> Application | None:
        self.purge_expired()
        with self._lock:
            app = self._apps.get(app_id)
            if app:
                app.last_seen = _now()
            return app

    def erase(self, app_id: str) -> bool:
        with self._lock:
            gone = self._apps.pop(app_id, None) is not None
        if gone:
            log.info("app=%s erased on owner request", app_id[:6])
        return gone

    def purge_expired(self) -> int:
        cutoff = _now() - self.retention
        with self._lock:
            old = [k for k, a in self._apps.items() if a.last_seen < cutoff]
            for k in old:
                del self._apps[k]
        if old:
            log.info("purged %d applications idle for more than %s", len(old), self.retention)
        return len(old)

    def all(self) -> list[Application]:
        with self._lock:
            return list(self._apps.values())

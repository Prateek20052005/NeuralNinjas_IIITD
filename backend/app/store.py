"""One owner's application from first chat message to KYC decision.

Saved so progress survives a server restart: with APP_STATE_DIR and APP_STATE_KEY set, every application is written
to its own file, encrypted and signed (Fernet: AES + HMAC), after each change, and read back at start-up. Without them
applications are kept in memory only (and are lost when the server restarts).

Privacy (DPDP Act 2023) by design:
- Document photos are read in memory and never written to disk; only the parsed fields are kept.
- KYC needs recorded consent first, for named purposes, with the consent text version and time.
- Applications (and their saved files) are deleted after RETENTION_HOURS without activity, or at once when the owner asks.
- The chat transcript is not kept: only the answers needed for the plan.
- Logs and screens only ever show masked identifiers; the mobile number is masked everywhere but the sales call list.
A real deployment would move this to an encrypted database; the rules stay the same.
"""
from __future__ import annotations

import logging
import os
import pickle
import secrets
import threading
from dataclasses import MISSING, dataclass, field, fields
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

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


def case_clock(at: datetime | None = None) -> datetime:
    """Time shown to people: the real time of day, on the case's date (APP_TODAY) when one is set.

    Prices, document validity and install dates are worked out from APP_TODAY, so the timeline must use the same
    calendar. Deleting data after the retention period always runs on the real clock."""
    at = at or _now()
    case = os.getenv("APP_TODAY")
    if not case:
        return at
    return at + timedelta(days=(date.fromisoformat(case) - datetime.now().date()).days)


@dataclass
class Consent:
    purposes: list[str]
    language: str
    version: str = CONSENT_VERSION
    given_at: str = field(default_factory=lambda: case_clock().isoformat(timespec="seconds"))


@dataclass
class Application:
    id: str
    session: Session
    items: dict[str, int] = field(default_factory=dict)       # bundle after the owner's add-on switches
    tier: str = "recommended"                                   # basic / recommended / full / custom
    contract_months: int | None = None                          # owner's choice; None = bundle minimum
    setup_months: int = 1                                       # setup fee paid at once (1) or spread
    billing_months: int = 1                                     # pay every 1, 3, 6 or 12 months
    discount_pct: float = 0.0                                   # negotiated on the plan screen (negotiate.py)
    price_asks: int = 0                                         # times the owner asked for a lower price
    callback: dict | None = None                                # salesperson call: phone kept only for that call
    phone: str | None = None                                    # verified mobile (OTP): resume + order updates
    phone_verified_at: str | None = None
    marketing_consent: bool = False                             # separate, unticked by default
    otp: dict | None = None                                     # pending code for this application (hash only)
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

    # saved files: the lock can't be saved, and files from an older version may lack newer fields
    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items() if k != "lock"}

    def __setstate__(self, state):
        for f in fields(self):
            if f.name not in state and f.name != "lock":
                state[f.name] = f.default_factory() if f.default_factory is not MISSING else f.default
        self.__dict__.update(state)
        self.lock = threading.Lock()

    def mark(self, step: str, **info) -> None:
        self.timeline.append({"step": step, "at": case_clock().isoformat(timespec="seconds"), **info})
        log.info("app=%s step=%s %s", self.id[:6], step, {k: mask(str(v)) if k in MASKED_FIELDS else v
                                                         for k, v in info.items()})


def masked_fields(doc: ParsedDoc) -> dict[str, str]:
    return {k: mask(v) if k in MASKED_FIELDS else v for k, v in doc.fields.items()}


class Store:
    def __init__(self, retention_hours: float | None = None, state_dir: str | None = None, key: str | None = None):
        hours = retention_hours if retention_hours is not None else float(os.getenv("RETENTION_HOURS", "72"))
        self.retention = timedelta(hours=hours)
        self._apps: dict[str, Application] = {}
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()          # saves take turns: two quick taps must not interleave writes
        self.resume_codes: dict[str, dict] = {}     # phone -> pending code for "continue a saved application"
        folder, key = state_dir or os.getenv("APP_STATE_DIR"), key or os.getenv("APP_STATE_KEY")
        self._dir, self._box = None, None
        if folder and key:
            from cryptography.fernet import Fernet
            self._dir, self._box = Path(folder), Fernet(key.encode())
            self._dir.mkdir(parents=True, exist_ok=True)
            self._load()
        else:
            log.warning("APP_STATE_DIR/APP_STATE_KEY not set: applications are kept in memory only")

    @property
    def saving(self) -> bool:
        return self._box is not None

    def _file(self, app_id: str) -> Path:
        return self._dir / f"{app_id}.app"

    def save(self, app_id: str) -> None:
        """Write one application to disk (encrypted). Called after every change."""
        if not self._box:
            return
        with self._save_lock:   # the newest state is always written last
            with self._lock:
                app = self._apps.get(app_id)
                if not app:
                    return
                data = self._box.encrypt(pickle.dumps(app))
            tmp = self._file(app_id).with_suffix(f".{secrets.token_hex(4)}.tmp")
            tmp.write_bytes(data)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._file(app_id))   # all or nothing: a crash never leaves half a file

    def _load(self) -> None:
        loaded = 0
        for f in self._dir.glob("*.app"):
            try:
                # files are only ever written by save(); the signature check stops anything else from being read
                app = pickle.loads(self._box.decrypt(f.read_bytes()))
            except Exception as e:
                log.warning("skipped a saved application that could not be read (%s)", type(e).__name__)
                continue
            self._apps[app.id] = app
            loaded += 1
        if loaded:
            log.info("loaded %d saved applications", loaded)
        self.purge_expired()

    def _forget(self, app_id: str) -> None:
        if self._dir:
            self._file(app_id).unlink(missing_ok=True)

    def create(self, session: Session) -> Application:
        app = Application(secrets.token_urlsafe(16), session)   # unguessable id: it is the owner's only key
        with self._lock:
            self._apps[app.id] = app
        self.save(app.id)
        return app

    def find_by_phone(self, phone: str) -> Application | None:
        """The most recently used application saved with this verified mobile number."""
        self.purge_expired()
        with self._lock:
            mine = [a for a in self._apps.values() if a.phone == phone and a.phone_verified_at]
        return max(mine, key=lambda a: a.last_seen) if mine else None

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
        self._forget(app_id)
        if gone:
            log.info("app=%s erased on owner request", app_id[:6])
        return gone

    def purge_expired(self) -> int:
        cutoff = _now() - self.retention
        with self._lock:
            old = [k for k, a in self._apps.items() if a.last_seen < cutoff]
            for k in old:
                del self._apps[k]
        for k in old:
            self._forget(k)
        if old:
            log.info("purged %d applications idle for more than %s", len(old), self.retention)
        return len(old)

    def all(self) -> list[Application]:
        with self._lock:
            return list(self._apps.values())

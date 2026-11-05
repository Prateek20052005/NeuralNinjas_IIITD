"""One-time codes to verify an owner's mobile number (save progress, resume on another phone, accept the plan).

Only a salted hash of the code is kept; a code expires after 10 minutes and allows 5 tries; a new code can be asked
for every 30 seconds, at most 5 times an hour (then the count starts again, so nobody is locked out for good). OTP_MODE=demo (the default) returns the code to the screen instead of sending
an SMS, for judging the prototype; OTP_MODE=sms sends it through an SMS provider (sms.py) and never shows it.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

CODE_TTL_SECONDS = 600
MAX_TRIES = 5
MAX_SENDS = 5
RESEND_AFTER_SECONDS = 30
SEND_WINDOW_SECONDS = 3600   # MAX_SENDS codes per number in this time


def stale(record: dict, now: float | None = None) -> bool:
    """True when a record no longer matters: its code has expired and its send count has run out."""
    now = now or time.time()
    return now > record["expires"] and now > record.get("first_sent", record["sent_at"]) + SEND_WINDOW_SECONDS


class OtpError(Exception):
    """code: wait | too_many | expired | wrong (an i18n key msg.otp_<code>); seconds: how long to wait."""

    def __init__(self, code: str, seconds: int = 0):
        super().__init__(code)
        self.code, self.seconds = code, seconds


def demo_mode() -> bool:
    """Only an explicit "demo" shows codes on screen; any other value means SMS (and fails safe if not set up)."""
    return os.getenv("OTP_MODE", "demo").strip().lower() == "demo"


def _digest(code: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


def issue(record: dict | None, phone: str, now: float | None = None) -> tuple[dict, str]:
    """A new code for this phone. record = the previous code's record (for the resend limits), or None."""
    now = now or time.time()
    sends, first_sent = 0, now
    if record and record.get("phone") == phone:
        wait = int(record["sent_at"] + RESEND_AFTER_SECONDS - now)
        if wait > 0:
            raise OtpError("wait", wait)
        first_sent = record.get("first_sent", record["sent_at"])
        if now < first_sent + SEND_WINDOW_SECONDS:
            sends = record["sends"]
            if sends >= MAX_SENDS:
                raise OtpError("too_many", int(first_sent + SEND_WINDOW_SECONDS - now))
        else:
            first_sent = now                     # a new hour: the count starts again
    code, salt = f"{secrets.randbelow(10 ** 6):06d}", secrets.token_hex(8)
    return {"phone": phone, "salt": salt, "hash": _digest(code, salt), "sent_at": now, "first_sent": first_sent,
            "expires": now + CODE_TTL_SECONDS, "tries": 0, "sends": sends + 1}, code


def check(record: dict | None, code: str, now: float | None = None) -> str:
    """Returns the verified phone number, or raises OtpError. A used code can't be used again."""
    now = now or time.time()
    if not record or record.get("used"):
        raise OtpError("expired")
    if now > record["expires"]:
        raise OtpError("expired")
    if record["tries"] >= MAX_TRIES:
        raise OtpError("too_many")
    record["tries"] += 1
    if not hmac.compare_digest(record["hash"], _digest(str(code).strip(), record["salt"])):
        raise OtpError("too_many" if record["tries"] >= MAX_TRIES else "wrong")
    record["used"] = True
    return record["phone"]

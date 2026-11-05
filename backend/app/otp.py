"""One-time codes to verify an owner's mobile number (save progress, resume on another phone, accept the plan).

Only a salted hash of the code is kept; a code expires after 10 minutes and allows 5 tries; a new code can be asked
for every 30 seconds, at most 5 times. OTP_MODE=demo (the default here, as the prototype has no SMS provider)
returns the code to the screen instead of sending an SMS; a real deployment sets OTP_MODE=sms and plugs in a provider.
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


class OtpError(Exception):
    """code: wait | too_many | expired | wrong (an i18n key msg.otp_<code>); seconds: how long to wait."""

    def __init__(self, code: str, seconds: int = 0):
        super().__init__(code)
        self.code, self.seconds = code, seconds


def demo_mode() -> bool:
    return os.getenv("OTP_MODE", "demo") == "demo"


def _digest(code: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


def issue(record: dict | None, phone: str, now: float | None = None) -> tuple[dict, str]:
    """A new code for this phone. record = the previous code's record (for the resend limits), or None."""
    now = now or time.time()
    sends = 0
    if record and record.get("phone") == phone:
        wait = int(record["sent_at"] + RESEND_AFTER_SECONDS - now)
        if wait > 0:
            raise OtpError("wait", wait)
        sends = record["sends"]
        if sends >= MAX_SENDS:
            raise OtpError("too_many")
    code, salt = f"{secrets.randbelow(10 ** 6):06d}", secrets.token_hex(8)
    if not demo_mode():
        raise NotImplementedError("OTP_MODE=sms needs an SMS provider; the prototype runs with OTP_MODE=demo")
    return {"phone": phone, "salt": salt, "hash": _digest(code, salt), "sent_at": now,
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

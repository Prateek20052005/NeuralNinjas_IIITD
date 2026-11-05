"""Sending one-time codes by SMS (OTP_MODE=sms). Demo mode (the default) sends nothing and shows the code on screen.

Providers (SMS_PROVIDER):
  msg91  - India. Indian SMS needs a DLT-registered sender ID and message template (TRAI rules); MSG91's OTP API sends
           our code through your approved template. Settings: MSG91_AUTH_KEY, MSG91_TEMPLATE_ID.
  twilio - Quick to try worldwide (a trial account can text only numbers you have verified with Twilio). Sends the text
           below. For Indian numbers in production, use a DLT-registered sender. Settings: TWILIO_ACCOUNT_SID,
           TWILIO_AUTH_TOKEN, and TWILIO_FROM (a Twilio number like +1415..., or a Messaging Service SID MG...).

Safety: if SMS is switched on but not set up, sending fails with an error; it never falls back to showing the code.
The code and the full number are never logged.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from .kyc.lookups import mask

log = logging.getLogger("sms")
TIMEOUT_SECONDS = 10
PROVIDERS = {"msg91": ("MSG91_AUTH_KEY", "MSG91_TEMPLATE_ID"),
             "twilio": ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM")}


class SmsError(Exception):
    """Sending failed or SMS is not set up; the owner is asked to try again later."""


def provider() -> str:
    return os.getenv("SMS_PROVIDER", "").strip().lower()


def missing_settings() -> list[str]:
    """Settings still needed for the chosen provider ([] = ready)."""
    name = provider()
    if name not in PROVIDERS:
        return ["SMS_PROVIDER (msg91 or twilio)"]
    return [key for key in PROVIDERS[name] if not os.getenv(key, "").strip()]


def _post(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, str]:
    """One HTTPS POST (kept separate so tests can stand in for the provider)."""
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _error_code(body: str) -> str:
    """The provider's error number from a refusal (Twilio: "code"), e.g. 21608 = number not verified on a trial."""
    try:
        reply = json.loads(body or "{}")
    except ValueError:
        return "?"
    code = reply.get("code") if isinstance(reply, dict) else None
    return str(code) if isinstance(code, int) else "?"


def send_code(phone: str, code: str, text: str) -> None:
    """Send `code` to the Indian mobile `phone` (10 digits). `text` = the full message, for providers that take one
    (MSG91 uses the DLT template registered with it instead). Raises SmsError on any failure."""
    gaps = missing_settings()
    if gaps:
        log.error("OTP_MODE=sms but SMS is not set up: missing %s", ", ".join(gaps))
        raise SmsError("not configured")
    name = provider()
    try:
        if name == "msg91":
            query = urllib.parse.urlencode({"template_id": os.environ["MSG91_TEMPLATE_ID"], "mobile": f"91{phone}",
                                            "otp": code, "otp_expiry": 10})
            status, body = _post(f"https://control.msg91.com/api/v5/otp?{query}", b"",
                                 {"authkey": os.environ["MSG91_AUTH_KEY"], "accept": "application/json"})
            ok = status == 200 and json.loads(body or "{}").get("type") == "success"
        else:   # twilio
            sid, token, sender = (os.environ[k] for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"))
            form = {"To": f"+91{phone}", "Body": text,
                    **({"MessagingServiceSid": sender} if sender.startswith("MG") else {"From": sender})}
            auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
            status, body = _post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                                 urllib.parse.urlencode(form).encode(),
                                 {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
            ok = status in (200, 201)
    except (OSError, ValueError) as e:   # network down, timeout, a reply that isn't JSON
        log.warning("SMS via %s to %s failed: %s", name, mask(phone), type(e).__name__)
        raise SmsError(type(e).__name__) from e
    if not ok:
        log.warning("SMS via %s to %s refused: HTTP %s, provider error %s", name, mask(phone), status,
                    _error_code(body))   # only the provider's error number, never the code or the body
        raise SmsError(f"HTTP {status}")
    log.info("SMS code sent via %s to %s", name, mask(phone))

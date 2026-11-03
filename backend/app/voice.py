"""Voice answers in the chat (English and Hindi for now): the owner's recording is turned into text by Groq Whisper.

Privacy: unlike typed text, audio can't have ID numbers removed before it leaves our server, so
  - the owner is warned before their first recording not to say private details (names, ID numbers, addresses),
  - the GST question has no microphone (the GST number is always typed, and read by our own code),
  - the recording is passed straight to Groq and never stored; neither the audio nor the text is logged,
  - the text comes back to the owner's screen to check and correct before it is sent as their answer.
Settings from .env: GROQ_API_KEY (same key as the chat), VOICE_MODEL.
"""
from __future__ import annotations

import logging
import os
import time

log = logging.getLogger("voice")

VOICE_LANGUAGES = ("en", "hi")          # add a language here once its voice flow has been checked
MAX_AUDIO_BYTES = 4_000_000             # ~30 s answers are far smaller; anything bigger is not a chat answer
AUDIO_EXTENSIONS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/x-m4a": "m4a",
                    "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav"}


class VoiceUnavailable(Exception):
    pass


class Transcriber:
    def __init__(self, client=None):
        self.client = client            # the Groq client the chat AI already uses (None = voice off)
        self.model = os.getenv("VOICE_MODEL") or "whisper-large-v3-turbo"

    @property
    def available(self) -> bool:
        return self.client is not None

    def transcribe(self, audio: bytes, content_type: str, language: str) -> str:
        if not self.client:
            raise VoiceUnavailable("no API key configured")
        ext = AUDIO_EXTENSIONS.get((content_type or "").split(";")[0].strip().lower(), "webm")
        start = time.time()
        try:
            out = self.client.audio.transcriptions.create(
                file=(f"answer.{ext}", audio), model=self.model, language=language,
                response_format="json", temperature=0.0)
        except Exception as e:   # rate limit, timeout, bad audio: the owner is asked to try again or type
            log.warning("voice failed (%s)", type(e).__name__)
            raise VoiceUnavailable(type(e).__name__) from e
        # only the size and time are logged: never the words
        log.info("voice ok bytes=%d secs=%.1f", len(audio), time.time() - start)
        return (getattr(out, "text", "") or "").strip()

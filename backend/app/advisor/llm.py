"""Thin wrapper around the chat AI (Groq by default). Any failure raises LLMUnavailable so callers can
fall back to the scripted flow; the owner never sees an AI error.

Settings come from .env: LLM_PROVIDER, GROQ_API_KEY, LLM_MODEL.
"""
from __future__ import annotations

import json
import logging
import os
import time

from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("advisor.llm")


class LLMUnavailable(Exception):
    pass


class LLM:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "groq")
        self.model = os.getenv("LLM_MODEL") or "openai/gpt-oss-120b"
        key = os.getenv("GROQ_API_KEY", "").strip()
        self.client = None
        if self.provider == "groq" and key:
            from groq import Groq
            self.client = Groq(api_key=key, timeout=20.0, max_retries=1)
        self.tokens_used = 0

    @property
    def available(self) -> bool:
        return self.client is not None

    def chat_json(self, system: str, messages: list[dict], max_tokens: int = 900) -> dict:
        """One chat call that must return a JSON object."""
        if not self.client:
            raise LLMUnavailable("no API key configured")
        start = time.time()
        for attempt in (1, 2):
            try:
                r = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, *messages],
                    response_format={"type": "json_object"},
                    reasoning_effort="low",
                    max_completion_tokens=max_tokens,
                )
                self.tokens_used += r.usage.total_tokens
                log.info("llm ok model=%s tokens=%s secs=%.1f", self.model, r.usage.total_tokens, time.time() - start)
                return json.loads(r.choices[0].message.content)
            except Exception as e:  # rate limit, timeout, bad JSON, network: all mean "use the scripted path"
                log.warning("llm failed (%s): %s", type(e).__name__, str(e)[:200])
                # Groq answers 400 when the model's JSON came out malformed; that is worth one more try
                if attempt == 1 and type(e).__name__ == "BadRequestError":
                    continue
                raise LLMUnavailable(type(e).__name__) from e

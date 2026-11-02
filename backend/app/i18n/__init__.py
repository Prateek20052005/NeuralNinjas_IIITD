"""Fixed screen text in English, Hindi and Marathi. Missing keys fall back to English."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LANGUAGES = {"en": "English", "hi": "हिंदी", "mr": "मराठी"}
_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def _strings(lang: str) -> dict[str, str]:
    path = _DIR / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def t(lang: str, key: str, **params) -> str:
    text = _strings(lang).get(key) or _strings("en").get(key) or key
    return text.format(**params) if params else text

"""Fixed screen text in English and six Indian languages, plus what the code needs to know about each script.
Missing keys fall back to English."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

# code: (name in its own script, English name for the AI prompt, Unicode block of its script; None = Latin)
_LANGS = {
    "en": ("English", "English", None),
    "hi": ("हिंदी", "Hindi (Devanagari script)", "ऀ-ॿ"),
    "mr": ("मराठी", "Marathi (Devanagari script)", "ऀ-ॿ"),
    "gu": ("ગુજરાતી", "Gujarati (Gujarati script)", "઀-૿"),
    "ta": ("தமிழ்", "Tamil (Tamil script)", "஀-௿"),
    "te": ("తెలుగు", "Telugu (Telugu script)", "ఀ-౿"),
    "kn": ("ಕನ್ನಡ", "Kannada (Kannada script)", "ಀ-೿"),
}
LANGUAGES = {code: v[0] for code, v in _LANGS.items()}
AI_LANGUAGE_NAMES = {code: v[1] for code, v in _LANGS.items()}
SCRIPT_RANGES = {code: v[2] for code, v in _LANGS.items() if v[2]}

# Any Indian script we support (for word boundaries and "is this a native-script word?")
INDIC = "".join(sorted(set(SCRIPT_RANGES.values())))
INDIC_RE = re.compile(f"[{INDIC}]")

# Digits owners may type in their own script: Devanagari, Gujarati, Tamil, Telugu, Kannada -> 0-9
_DIGIT_SETS = ["०१२३४५६७८९", "૦૧૨૩૪૫૬૭૮૯", "௦௧௨௩௪௫௬௭௮௯", "౦౧౨౩౪౫౬౭౮౯", "೦೧೨೩೪೫೬೭೮೯"]
_TO_ASCII = str.maketrans({d: str(i) for digits in _DIGIT_SETS for i, d in enumerate(digits)})
INDIC_DIGITS = "".join(_DIGIT_SETS)


def ascii_digits(text: str) -> str:
    """'४ लोग', '೪ ಜನ', '௪' -> '4 ...': numbers typed in any supported script."""
    return str(text).translate(_TO_ASCII)


def script_share(text: str, lang: str) -> tuple[int, int]:
    """(letters in the language's own script, Latin letters) in the text."""
    own = len(re.findall(f"[{SCRIPT_RANGES[lang]}]", text)) if lang in SCRIPT_RANGES else 0
    return own, len(re.findall(r"[A-Za-z]", text))


_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def _strings(lang: str) -> dict[str, str]:
    path = _DIR / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def t(lang: str, key: str, **params) -> str:
    text = _strings(lang).get(key) or _strings("en").get(key) or key
    return text.format(**params) if params else text

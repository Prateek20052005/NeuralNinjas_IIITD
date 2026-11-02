"""Understand short answers (numbers, yes/no) in English, Hindi and Marathi, in Devanagari or English letters."""
from __future__ import annotations

import re

YES = {"yes", "y", "yeah", "yep", "sure", "true", "haan", "han", "ha", "ho", "hoy", "ji", "हाँ", "हां", "जी", "हो", "होय"}
NO = {"no", "n", "nope", "not", "don't", "dont", "without", "false", "nahi", "nahin", "nai", "naahi",
      "नहीं", "नही", "नाही", "नको"}
NUMBER_WORDS = {
    1: {"one", "single", "ek", "एक", "akela", "only", "एकच", "ekach"}, 2: {"two", "do", "don", "दो", "दोन", "दोनच"},
    3: {"three", "teen", "tin", "तीन", "तीनच"}, 4: {"four", "char", "chaar", "चार"}, 5: {"five", "paanch", "panch", "पाँच", "पांच", "पाच"},
    6: {"six", "chhe", "chah", "छह", "सहा"}, 7: {"seven", "saat", "सात"}, 8: {"eight", "aath", "आठ"},
    9: {"nine", "nau", "नौ", "नऊ"}, 10: {"ten", "das", "दस", "दहा"},
    11: {"eleven"}, 12: {"twelve", "barah"}, 15: {"fifteen", "pandrah"}, 20: {"twenty", "bees", "बीस", "वीस"},
    30: {"thirty", "tees", "तीस"}, 40: {"forty", "chalis", "चालीस"}, 50: {"fifty", "pachas", "पचास", "पन्नास"},
    100: {"hundred", "sau", "सौ", "शंभर"},
}
TENS = {20, 30, 40, 50}

# Words owners type for their kind of business -> segment. Checked in this order, so "pharmacy chain" is multi.
# Latin stems match at the start of a word; Devanagari stems anywhere.
KIND_WORDS = {
    "multi": ["chain", "outlets", "branches", "franchise", "चेन", "शाखा", "आउटलेट"],
    "mfg": ["factory", "manufactur", "workshop", "plant", "mill", "moulding", "molding", "fabricat", "industr",
            "karkhana", "kaarkhana", "printing press", "packaging", "textile", "food processing", "auto parts",
            "auto-parts", "कारखाना", "कारख़ाना", "फैक्ट्री", "फ़ैक्टरी", "फॅक्टरी", "उद्योग", "वर्कशॉप", "कार्यशाळा"],
    "prof": ["clinic", "doctor", "dentist", "dental", "diagnostic", "lab", "physio", "hospital", "ca ", "ca firm",
             "chartered", "accountant", "lawyer", "advocate", "law", "legal", "coaching", "tuition", "classes",
             "academy", "office", "agency", "consult", "architect", "studio", "insurance", "travel", "real estate",
             "daftar", "vakil", "dawakhana", "क्लिनिक", "डॉक्टर", "दवाखाना", "कोचिंग", "ट्यूशन", "क्लासेस", "ऑफिस",
             "दफ्तर", "दफ़्तर", "कार्यालय", "वकील", "सीए", "कचेरी", "एजन्सी", "एजेंसी", "लैब", "लॅब"],
    "micro": ["shop", "store", "kirana", "grocery", "salon", "parlour", "parlor", "pharmacy", "medical", "chemist",
              "bakery", "boutique", "tailor", "sweet", "mithai", "optician", "stationery", "hardware", "repair",
              "cafe", "dhaba", "restaurant", "dukan", "dukaan", "दुकान", "किराना", "किराणा", "सैलून", "सलून",
              "पार्लर", "दवाई", "दवा", "मेडिकल", "केमिस्ट", "फार्मेसी", "बेकरी", "मिठाई", "दर्जी", "स्टोर",
              "औषध", "शिंपी", "हॉटेल", "ढाबा"],
}
SHOP_WORDS = ("shop", "store", "outlet", "branch", "dukan", "dukaan", "दुकान", "शाखा", "स्टोर")


def _words(text) -> set[str]:
    return {w.strip(".,!?।") for w in str(text).lower().split()}


def number(text) -> int | None:
    """First number in the text, as digits (any script) or a number word; None if there is none."""
    s = str(text).translate(str.maketrans("०१२३४५६७८९", "0123456789")).lower()
    m = re.search(r"\d+", s)
    if m:
        return int(m.group(0))
    found = [n for n, names in NUMBER_WORDS.items() if _words(s) & names]
    if not found:
        return None
    tens = [n for n in found if n in TENS]
    ones = [n for n in found if n < 10]
    if tens and ones:            # "twenty five" -> 25
        return tens[0] + ones[0]
    return max(found)


def kind_of_business(text) -> str | None:
    """'kirana store' -> 'micro', 'कापड कारखाना' -> 'mfg', 'kapdon ki 6 dukaanein' -> 'multi'; None if unclear."""
    s = f" {str(text).lower()} "
    for kind, stems in KIND_WORDS.items():
        if any((stem in s) if re.search(r"[ऀ-ॿ]", stem) else re.search(rf"(?<![a-z]){re.escape(stem)}", s)
               for stem in stems):
            n = number(text)
            if kind in ("micro", "prof") and n and n >= 3 and any(w in s for w in SHOP_WORDS):
                return "multi"   # "we have 4 shops"
            return kind
    return None


def yes_no(text) -> bool | None:
    """True / False for a clear yes or no; None if unclear. 'No' wins if both appear."""
    words = _words(text)
    if words & NO:
        return False
    if words & YES:
        return True
    return None

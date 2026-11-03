"""Lookup tables derived from the leads data: business type -> segment, city -> tier."""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from functools import lru_cache

from .catalogue import DATA_DIR, SEGMENTS
from .i18n import INDIC

SEGMENT_CODE = {v: k for k, v in SEGMENTS.items()}


@lru_cache(maxsize=1)
def _tables():
    types, cities = defaultdict(Counter), defaultdict(Counter)
    with open(DATA_DIR / "smb_leads.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            types[r["business_type"]][SEGMENT_CODE[r["segment"]]] += 1
            cities[r["city"]][(int(r["city_tier"]), r["state"])] += 1
    business_types = {t: c.most_common(1)[0][0] for t, c in types.items()}
    city_info = {c: v.most_common(1)[0][0] for c, v in cities.items()}
    return business_types, city_info


def business_types() -> dict[str, str]:
    """{'Dental clinic': 'prof', 'Kirana store': 'micro', ...}"""
    return _tables()[0]


def cities() -> dict[str, tuple[int, str]]:
    """{'Pune': (1, 'Maharashtra'), 'Nagpur': (2, 'Maharashtra'), ...}"""
    return _tables()[1]


# Hindi/Marathi spellings and old or short names owners type, mapped to the names used in the data
CITY_ALIASES = {
    "कोच्चि": "Kochi", "कोची": "Kochi", "cochin": "Kochi", "लुधियाना": "Ludhiana", "चेन्नई": "Chennai",
    "madras": "Chennai", "नागपुर": "Nagpur", "नागपूर": "Nagpur", "जयपुर": "Jaipur", "जयपूर": "Jaipur",
    "विशाखापत्तनम": "Visakhapatnam", "vizag": "Visakhapatnam", "लखनऊ": "Lucknow", "भोपाल": "Bhopal",
    "कोलकाता": "Kolkata", "calcutta": "Kolkata", "पुणे": "Pune", "पूना": "Pune", "poona": "Pune",
    "सूरत": "Surat", "हैदराबाद": "Hyderabad", "बेंगलुरु": "Bengaluru", "बेंगलूरु": "Bengaluru",
    "बंगलौर": "Bengaluru", "bangalore": "Bengaluru", "मुंबई": "Mumbai", "बंबई": "Mumbai", "bombay": "Mumbai",
    "मैसूर": "Mysuru", "mysore": "Mysuru", "अहमदाबाद": "Ahmedabad", "कोयंबटूर": "Coimbatore",
    "इंदौर": "Indore", "नाशिक": "Nashik", "नासिक": "Nashik", "nasik": "Nashik", "दिल्ली": "Delhi",
    "new delhi": "Delhi", "नई दिल्ली": "Delhi", "वडोदरा": "Vadodara", "बड़ौदा": "Vadodara",
    "baroda": "Vadodara", "पटना": "Patna",
    # Gujarati, Tamil, Telugu and Kannada. Stems without the last vowel where the name takes endings
    # ("ಬೆಂಗಳೂರಿನಲ್ಲಿ" = in Bengaluru), since names are found as a prefix inside the owner's words.
    "ಬೆಂಗಳೂರ": "Bengaluru", "బెంగళూర": "Bengaluru", "பெங்களூர": "Bengaluru", "બેંગલોર": "Bengaluru", "બેંગલુરુ": "Bengaluru",
    "ಮೈಸೂರ": "Mysuru", "మైసూర": "Mysuru", "மைசூர": "Mysuru", "મૈસુર": "Mysuru",
    "ಚೆನ್ನೈ": "Chennai", "చెన్నై": "Chennai", "சென்னை": "Chennai", "ચેન્નાઈ": "Chennai", "ચેન્નઈ": "Chennai",
    "ಕೊಯಮತ್ತೂರ": "Coimbatore", "కోయంబత్తూర": "Coimbatore", "கோயம்புத்தூர": "Coimbatore", "கோவை": "Coimbatore",
    "kovai": "Coimbatore", "કોઇમ્બતુર": "Coimbatore",
    "ಹೈದರಾಬಾದ": "Hyderabad", "హైదరాబాద": "Hyderabad", "ஹைதராபாத": "Hyderabad", "હૈદરાબાદ": "Hyderabad",
    "ವಿಶಾಖಪಟ್ಟಣ": "Visakhapatnam", "విశాఖపట్న": "Visakhapatnam", "విశాఖ": "Visakhapatnam", "వైజాగ్": "Visakhapatnam",
    "விசாகப்பட்டின": "Visakhapatnam", "વિશાખાપટ્ટનમ": "Visakhapatnam",
    "ಅಹಮದಾಬಾದ": "Ahmedabad", "అహ్మదాబాద": "Ahmedabad", "அகமதாபாத": "Ahmedabad", "અમદાવાદ": "Ahmedabad",
    "ಸೂರತ": "Surat", "సూరత": "Surat", "சூரத": "Surat", "સુરત": "Surat",
    "ವಡೋದರ": "Vadodara", "వడోదర": "Vadodara", "வதோதர": "Vadodara", "વડોદરા": "Vadodara", "બરોડા": "Vadodara",
    "ಮುಂಬೈ": "Mumbai", "ముంబై": "Mumbai", "மும்பை": "Mumbai", "મુંબઈ": "Mumbai", "મુંબઇ": "Mumbai",
    "ದೆಹಲಿ": "Delhi", "ఢిల్లీ": "Delhi", "டெல்லி": "Delhi", "દિલ્હી": "Delhi",
    "ಪುಣೆ": "Pune", "పూణే": "Pune", "పుణే": "Pune", "புனே": "Pune", "પુણે": "Pune", "પૂના": "Pune",
    "ಕೊಚ್ಚಿ": "Kochi", "కొచ్చి": "Kochi", "கொச்சி": "Kochi", "કોચી": "Kochi",
    "ಕೋಲ್ಕತ್ತಾ": "Kolkata", "కోల్‌కతా": "Kolkata", "கொல்கத்தா": "Kolkata", "કોલકાતા": "Kolkata",
    "ಜೈಪುರ": "Jaipur", "జైపూర": "Jaipur", "ஜெய்ப்பூர": "Jaipur", "જયપુર": "Jaipur",
    "ಇಂದೋರ": "Indore", "ఇండోర": "Indore", "இந்தூர": "Indore", "ઇન્દોર": "Indore",
    "ನಾಗಪುರ": "Nagpur", "నాగపూర": "Nagpur", "நாக்பூர": "Nagpur", "નાગપુર": "Nagpur",
}


def canonical_city(city: str) -> str:
    """'पुणे', 'poona', 'PUNE' -> 'Pune'. Unknown towns come back trimmed and title-cased."""
    raw = city.strip()
    known = {c.lower(): c for c in cities()}
    return known.get(raw.lower()) or CITY_ALIASES.get(raw.lower()) or CITY_ALIASES.get(raw) or raw.title()


FILLER_WORDS = {"we", "are", "i", "am", "in", "at", "from", "based", "our", "my", "city", "is", "the", "shop", "business",
                 "located", "it's", "its", "hum", "main", "mein", "me", "hai", "hain", "se", "में", "मैं", "है", "हैं",
                 "से", "हम", "हमारा", "शहर", "आहे", "मध्ये", "आम्ही", "माझं", "माझे", "आमचं", "शहरात",
                 "અમે", "હું", "છીએ", "છે", "અમારું", "અમારી", "શહેર", "ગામ", "நாங்கள்", "நான்", "இருக்கிறோம்", "இருக்கு",
                 "எங்கள்", "ஊர்", "நகரம்", "మేము", "నేను", "ఉన్నాము", "ఉంది", "మా", "ఊరు", "నగరం", "ನಾವು", "ನಾನು",
                 "ಇದ್ದೇವೆ", "ಇದೆ", "ನಮ್ಮ", "ಊರು", "ನಗರ"}


def find_city(text: str, known_only: bool = False) -> str | None:
    """The city in a typed answer: 'We are in Chennai' -> 'Chennai', 'हम नाशिक में हैं' -> 'Nashik'.
    A known city anywhere in the text wins; otherwise a short answer (not a question) is taken as the town's name."""
    s = f" {text.lower()} "
    names = {c.lower(): c for c in cities()} | {k.lower(): v for k, v in CITY_ALIASES.items()}
    for name in sorted(names, key=len, reverse=True):
        if re.search(rf"(?<![\w{INDIC}]){re.escape(name)}", s):
            return names[name]
    if known_only or "?" in text:
        return None
    words = [w for w in re.findall(rf"[\w{INDIC}'.-]+", text) if w.lower() not in FILLER_WORDS]
    return canonical_city(" ".join(words)) if 1 <= len(words) <= 3 else None


def city_tier(city: str, default: int = 2) -> int:
    """Unknown towns default to tier 2 so we never offer a tier-1-only product by mistake."""
    return cities().get(canonical_city(city), (default, None))[0]

"""Understand short answers (numbers, yes/no, kind of business, internet) in English, Hindi, Marathi, Gujarati,
Tamil, Telugu and Kannada, typed in the language's own script or in English letters ("haan", "haudu", "illai")."""
from __future__ import annotations

import re

from ..i18n import INDIC_RE, ascii_digits

YES = {"yes", "y", "yeah", "yep", "sure", "true", "haan", "han", "ha", "ho", "hoy", "ji", "हाँ", "हां", "जी", "हो", "होय",
       # Gujarati
       "હા", "હાં", "જી", "જોઈએ", "જરૂર", "haa", "joie",
       # Tamil
       "ஆம்", "ஆமா", "ஆமாம்", "சரி", "வேண்டும்", "வேணும்", "தேவை", "aama", "aamaa", "aamam", "sari", "venum", "vendum",
       # Telugu
       "అవును", "అవునండి", "సరే", "కావాలి", "avunu", "avnu", "sare", "kavali", "kaavali",
       # Kannada
       "ಹೌದು", "ಹೂಂ", "ಸರಿ", "ಬೇಕು", "ಅಗತ್ಯ", "haudu", "howdu", "beku",
       # Hindi / Marathi / Hinglish "want it", "of course"
       "chahiye", "chahie", "chaiye", "चाहिए", "चाहिये", "pahije", "पाहिजे", "zaroor", "zarur", "jarur", "जरूर",
       "ज़रूर", "bilkul", "बिल्कुल", "ok", "okay"}
NO = {"no", "n", "nope", "not", "don't", "dont", "without", "false", "nahi", "nahin", "nai", "naahi",
      "नहीं", "नही", "नाही", "नको",
      "ના", "નહીં", "નહિ", "નથી", "nathi",
      "இல்லை", "இல்ல", "வேண்டாம்", "வேணாம்", "தேவையில்லை", "illai", "illa", "vendam", "venam", "vendaam",
      "లేదు", "కాదు", "వద్దు", "లేవు", "అక్కర్లేదు", "ledu", "kaadu", "vaddu",
      "ಇಲ್ಲ", "ಬೇಡ", "ಅಲ್ಲ", "ಬೇಕಾಗಿಲ್ಲ", "ಅಗತ್ಯವಿಲ್ಲ", "beda", "alla"}
NUMBER_WORDS = {
    1: {"one", "single", "ek", "एक", "akela", "only", "एकच", "ekach"}, 2: {"two", "do", "don", "दो", "दोन", "दोनच"},
    3: {"three", "teen", "tin", "तीन", "तीनच"}, 4: {"four", "char", "chaar", "चार"}, 5: {"five", "paanch", "panch", "पाँच", "पांच", "पाच"},
    6: {"six", "chhe", "chah", "छह", "सहा"}, 7: {"seven", "saat", "सात"}, 8: {"eight", "aath", "आठ"},
    9: {"nine", "nau", "नौ", "नऊ"}, 10: {"ten", "das", "दस", "दहा"},
    11: {"eleven"}, 12: {"twelve", "barah"}, 15: {"fifteen", "pandrah"}, 20: {"twenty", "bees", "बीस", "वीस"},
    30: {"thirty", "tees", "तीस"}, 40: {"forty", "chalis", "चालीस"}, 50: {"fifty", "pachas", "पचास", "पन्नास"},
    100: {"hundred", "sau", "सौ", "शंभर"},
}
# Gujarati, Tamil, Telugu and Kannada number words (and "only one", "two people", ...)
for n, words in {
    1: {"એક", "એકજ", "ஒன்று", "ஒரு", "ஒரே", "ஒருவர்", "ஒன்னு", "ఒకటి", "ఒక", "ఒక్కటే", "ఒక్కరే", "ಒಂದು", "ಒಂದೇ", "ಒಬ್ಬ",
        "ಒಬ್ಬರೇ", "onnu", "okati", "ondu"},
    2: {"બે", "இரண்டு", "ரெண்டு", "இருவர்", "రెండు", "ఇద్దరు", "ಎರಡು", "ಇಬ್ಬರು", "rendu", "eradu"},
    3: {"ત્રણ", "மூன்று", "மூணு", "మూడు", "ముగ్గురు", "ಮೂರು", "ಮೂವರು", "moonu", "moodu", "mooru"},
    4: {"ચાર", "நான்கு", "நாலு", "నాలుగు", "నలుగురు", "ನಾಲ್ಕು", "ನಾಲ್ವರು", "naalu", "naalugu", "naalku"},
    5: {"પાંચ", "ஐந்து", "அஞ்சு", "ఐదు", "ఐదుగురు", "ಐದು", "anju", "aidu"},
    6: {"છ", "ஆறு", "ఆరు", "ಆರು"}, 7: {"સાત", "ஏழு", "ఏడు", "ಏಳು"}, 8: {"આઠ", "எட்டு", "ఎనిమిది", "ಎಂಟು"},
    9: {"નવ", "ஒன்பது", "తొమ్మిది", "ಒಂಬತ್ತು"}, 10: {"દસ", "பத்து", "పది", "ಹತ್ತು", "pathu", "padi", "hattu"},
    12: {"બાર", "பன்னிரண்டு", "పన్నెండు", "ಹನ್ನೆರಡು"}, 15: {"પંદર", "பதினைந்து", "పదిహేను", "ಹದಿನೈದು"},
    20: {"વીસ", "இருபது", "ఇరవై", "ಇಪ್ಪತ್ತು"}, 30: {"ત્રીસ", "முப்பது", "ముప్పై", "ಮೂವತ್ತು"},
    40: {"ચાલીસ", "நாற்பது", "నలభై", "ನಲವತ್ತು"}, 50: {"પચાસ", "ஐம்பது", "యాభై", "ಐವತ್ತು"},
    100: {"સો", "நூறு", "వంద", "ನೂರು"},
}.items():
    NUMBER_WORDS.setdefault(n, set()).update(words)
TENS = {20, 30, 40, 50}

# Words owners type for their kind of business -> segment. Checked in this order, so "pharmacy chain" is multi.
# Latin stems match at the start of a word; Indian-script stems anywhere (so "ಅಂಗಡಿಯಲ್ಲಿ" still finds "ಅಂಗಡಿ").
KIND_WORDS = {
    "multi": ["chain", "outlets", "branches", "franchise", "चेन", "शाखा", "आउटलेट",
              "શાખા", "બ્રાન્ચ", "ચેઇન", "கிளை", "பிராஞ்ச்", "செயின்", "శాఖ", "బ్రాంచ్", "చైన్", "ఔట్‌లెట్",
              "ಶಾಖೆ", "ಬ್ರಾಂಚ್", "ಚೈನ್"],
    "mfg": ["factory", "manufactur", "workshop", "plant", "mill", "moulding", "molding", "fabricat", "industr",
            "karkhana", "kaarkhana", "printing press", "packaging", "textile", "food processing", "auto parts",
            "auto-parts", "कारखाना", "कारख़ाना", "फैक्ट्री", "फ़ैक्टरी", "फॅक्टरी", "उद्योग", "वर्कशॉप", "कार्यशाळा",
            "karkhane", "ફેક્ટરી", "કારખાન", "વર્કશોપ", "ઉદ્યોગ", "தொழிற்சாலை", "ஃபேக்டரி", "பேக்டரி", "பட்டறை",
            "வொர்க்ஷாப்", "உற்பத்தி", "ఫ్యాక్టరీ", "కర్మాగార", "వర్క్‌షాప్", "వర్క్షాప్", "వర్క్ షాప్", "పరిశ్రమ",
            "ಕಾರ್ಖಾನೆ", "ಫ್ಯಾಕ್ಟರಿ", "ವರ್ಕ್‌ಶಾಪ್", "ವರ್ಕ್ಶಾಪ್", "ವರ್ಕ್ ಶಾಪ್"],
    "prof": ["clinic", "doctor", "dentist", "dental", "diagnostic", "lab", "physio", "hospital", "ca ", "ca firm",
             "chartered", "accountant", "lawyer", "advocate", "law", "legal", "coaching", "tuition", "classes",
             "academy", "office", "agency", "consult", "architect", "studio", "insurance", "travel", "real estate",
             "daftar", "vakil", "dawakhana", "क्लिनिक", "डॉक्टर", "दवाखाना", "कोचिंग", "ट्यूशन", "क्लासेस", "ऑफिस",
             "दफ्तर", "दफ़्तर", "कार्यालय", "वकील", "सीए", "कचेरी", "एजन्सी", "एजेंसी", "लैब", "लॅब",
             "ક્લિનિક", "ડૉક્ટર", "ડોક્ટર", "હોસ્પિટલ", "દવાખાન", "ઓફિસ", "ઑફિસ", "કચેરી", "કોચિંગ", "ટ્યુશન", "વકીલ", "સીએ",
             "கிளினிக்", "டாக்டர்", "மருத்துவர்", "மருத்துவமனை", "ஹாஸ்பிடல்", "அலுவலக", "ஆபீஸ்", "ஆஃபீஸ்", "கோச்சிங்",
             "டியூஷன்", "ட்யூஷன்", "வழக்கறிஞர்", "வக்கீல்", "ஆடிட்டர்",
             "క్లినిక్", "డాక్టర్", "ఆసుపత్రి", "హాస్పిటల్", "ఆఫీస్", "ఆఫీసు", "కార్యాలయ", "కోచింగ్", "ట్యూషన్", "లాయర్",
             "న్యాయవాది", "ఆడిటర్",
             "ಕ್ಲಿನಿಕ್", "ಡಾಕ್ಟರ್", "ವೈದ್ಯ", "ಆಸ್ಪತ್ರೆ", "ಆಫೀಸ್", "ಕಚೇರಿ", "ಕೋಚಿಂಗ್", "ಟ್ಯೂಷನ್", "ವಕೀಲ", "ಆಡಿಟರ್"],
    "micro": ["shop", "store", "kirana", "grocery", "salon", "parlour", "parlor", "pharmacy", "medical", "chemist",
              "bakery", "boutique", "tailor", "sweet", "mithai", "optician", "stationery", "hardware", "repair",
              "cafe", "dhaba", "restaurant", "dukan", "dukaan", "दुकान", "किराना", "किराणा", "सैलून", "सलून",
              "पार्लर", "दवाई", "दवा", "मेडिकल", "केमिस्ट", "फार्मेसी", "बेकरी", "मिठाई", "दर्जी", "स्टोर",
              "औषध", "शिंपी", "हॉटेल", "ढाबा", "angadi", "kadai", "maligai", "dinasi",
              "દુકાન", "કરિયાણા", "કિરાણા", "મેડિકલ", "દવા", "સલૂન", "સલુન", "હોટલ", "રેસ્ટોરન્ટ", "બેકરી", "દરજી", "મીઠાઈ",
              "સ્ટોર", "கடை", "ஷாப்", "மளிகை", "மெடிக்கல்", "மருந்து", "சலூன்", "ஹோட்டல்", "உணவகம்", "பேக்கரி",
              "டெய்லர்", "தையல்", "ஸ்டோர்", "దుకాణ", "షాప్", "కిరాణా", "మెడికల్", "ఫార్మసీ", "సెలూన్", "హోటల్",
              "రెస్టారెంట్", "బేకరీ", "టైలర్", "స్టోర్", "ಅಂಗಡಿ", "ಶಾಪ್", "ಕಿರಾಣಿ", "ದಿನಸಿ", "ಮೆಡಿಕಲ್", "ಫಾರ್ಮಸಿ",
              "ಔಷಧ", "ಸಲೂನ್", "ಹೋಟೆಲ್", "ಬೇಕರಿ", "ಟೈಲರ್", "ದರ್ಜಿ", "ಸ್ಟೋರ್"],
}
SHOP_WORDS = ("shop", "store", "outlet", "branch", "dukan", "dukaan", "दुकान", "शाखा", "स्टोर", "angadi", "kadai",
              "દુકાન", "શાખા", "கடை", "கிளை", "దుకాణ", "షాప్", "శాఖ", "ಅಂಗಡಿ", "ಶಾಖೆ")


def _words(text) -> set[str]:
    return {w.strip(".,!?।") for w in str(text).lower().split()}


def number(text) -> int | None:
    """First number in the text, as digits (any script) or a number word; None if there is none."""
    s = ascii_digits(text).lower()
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
        if any((stem in s) if INDIC_RE.search(stem) else re.search(rf"(?<![a-z]){re.escape(stem)}", s)
               for stem in stems):
            n = shop_count(text)
            if kind in ("micro", "prof") and n and n >= 3:
                return "multi"   # "we have 4 shops"
            return kind
    return None


def shop_count(text) -> int | None:
    """The number written next to a shop word: "4 shops", "kapdon ki 6 dukaanein", "एक ही दुकान" (1). A staff count
    in the same message ("one shop, 4 staff", "medicine shop, four of us work here") is not a shop count."""
    tokens = [w.strip(".,!?।:;()\"'") for w in str(text).lower().split()]
    for i, w in enumerate(tokens):
        if any(stem in w for stem in SHOP_WORDS):
            for j in (i - 1, i - 2):   # "4 shops", "ek hi dukan"
                if j >= 0 and (n := number(tokens[j])) is not None:
                    return n
    return None


# Kannada, Tamil and Telugu often put "not" in the verb ending: "ಮಾಡಿಸಿಲ್ಲ" (haven't done), "எடுக்கவில்லை"
# (haven't taken), "చేయలేదు" (didn't do). "ಿಲ್ಲ" (with the i-sign) so that "ಎಲ್ಲ" (all) is not read as no.
NO_ENDINGS = ("ಿಲ್ಲ", "ில்லை", "ில்ல", "లేదు")


# "na" is Gujarati (and Hindi) for no, but in Hinglish it is also a tag after a verb: "haan na", "chahiye na",
# "lagwa do na" all mean yes. So it means no only when the answer starts with it ("na", "na bhai", "na, nahi").
TAG_NO = {"na", "naa", "ना"}


def yes_no(text) -> bool | None:
    """True / False for a clear yes or no; None if unclear. 'No' wins if both appear."""
    order = [w.strip(".,!?।") for w in str(text).lower().split()]
    words = set(order)
    if words & NO or any(w.endswith(NO_ENDINGS) for w in words) or (order and order[0] in TAG_NO):
        return False
    if words & YES:
        return True
    return None


# Typed answers to "What internet connection do you need?"
INTERNET_WORDS = {
    "unsure": ["not sure", "don't know", "dont know", "no idea", "pata nahi", "pata nahin", "nahi pata", "malum nahi",
               "पता नहीं", "नहीं पता", "मालूम नहीं", "माहित नाही", "माहीत नाही", "शायद", "maybe",
               "ખબર નથી", "ખબર નહીં", "ખબર નહિ", "khabar nathi", "தெரியாது", "தெரியல", "theriyadhu", "theriyathu",
               "తెలియదు", "తెలీదు", "teliyadu", "ಗೊತ್ತಿಲ್ಲ", "gottilla"],
    "wireless": ["5g", "wireless", "airfiber", "air fiber", "वायरलेस", "एयरफाइबर", "एअरफायबर", "વાયરલેસ", "வயர்லெஸ்",
                 "వైర్‌లెస్", "వైర్లెస్", "ವೈರ್‌ಲೆಸ್", "ವೈರ್ಲೆಸ್"],
    "mobile": ["mobile", "sim", "phone line", "मोबाइल", "मोबाईल", "सिम", "फोन लाइन", "મોબાઇલ", "મોબાઈલ", "સિમ", "સીમ",
               "மொபைல்", "சிம்", "మొబైల్", "సిమ్", "ಮೊಬೈಲ್", "ಸಿಮ್"],
    "fibre": ["fibre", "fiber", "wired", "broadband", "wifi", "wi-fi", "फाइबर", "फायबर", "ब्रॉडबैंड", "ब्रॉडबँड",
              "वाईफाई", "वाई-फाई", "ફાઇબર", "ફાયબર", "બ્રોડબેન્ડ", "વાઇફાઇ", "ஃபைபர்", "பைபர்", "பிராட்பேண்ட்", "வைஃபை",
              "ఫైబర్", "బ్రాడ్‌బ్యాండ్", "వైఫై", "ಫೈಬರ್", "ಬ್ರಾಡ್‌ಬ್ಯಾಂಡ್", "ವೈಫೈ"],
    "internet": ["internet", "इंटरनेट", "ઇન્ટરનેટ", "இணைய", "இன்டர்நெட்", "இண்டர்நெட்", "ఇంటర్నెట్", "ಇಂಟರ್ನೆಟ್"],
}


def _has(s: str, stems: list[str]) -> bool:
    """Devanagari stems anywhere; English words whole (plural allowed), so 'simple' is not 'sim'."""
    return any((stem in s) if INDIC_RE.search(stem) else re.search(rf"(?<![a-z0-9]){re.escape(stem)}s?(?![a-z])", s)
               for stem in stems)


def internet_choice(text) -> str | None:
    """'fibre' | 'wireless' | 'unsure' | 'mobile', or None if unclear.
    'no fibre here' -> wireless, 'sirf mobile sim' / 'internet nahi chahiye' -> mobile."""
    s = f" {str(text).lower()} "
    if s.strip() in ("fibre", "wireless", "unsure", "mobile"):   # tapped option
        return s.strip()
    if _has(s, INTERNET_WORDS["unsure"]):
        return "unsure"
    if _has(s, INTERNET_WORDS["wireless"]):
        return "wireless"
    fibre, no = _has(s, INTERNET_WORDS["fibre"]), yes_no(text) is False
    if fibre:
        return "wireless" if no else "fibre"
    if _has(s, INTERNET_WORDS["mobile"]) or (no and _has(s, INTERNET_WORDS["internet"])):
        return "mobile"
    return None


CURRENT_WORDS = {
    "leased": ["leased", "lease line", "ill", "लीज़्ड", "लीज्ड", "લીઝ્ડ", "லீஸ்டு", "లీజ్డ్", "ಲೀಸ್ಡ್"],
    "home": ["home", "ghar", "घर", "ઘર", "வீட்டு", "ఇంటి", "ಮನೆ"],
    "business": ["business", "office", "बिज़नेस", "बिजनेस", "बिझनेस", "ऑफिस", "ઓફિસ", "બિઝનેસ", "ஆபீஸ்", "பிசினஸ்",
                 "బిజినెస్", "ఆఫీస్", "ಬಿಸಿನೆಸ್", "ಆಫೀಸ್"],
    "mobile": ["hotspot", "data", "हॉटस्पॉट", "डेटा", "હોટસ્પોટ", "ડેટા", "ஹாட்ஸ்பாட்", "டேட்டா", "హాట్‌స్పాట్",
               "డేటా", "ಹಾಟ್‌ಸ್ಪಾಟ್", "ಡೇಟಾ"] + INTERNET_WORDS["mobile"],
    "none": ["nothing", "none", "kuch nahi", "कुछ नहीं", "काही नाही", "કંઈ નથી", "எதுவும் இல்லை", "ఏమీ లేదు", "ಏನೂ ಇಲ್ಲ"],
}


def current_tools_choice(text) -> str | None:
    """What the owner uses for internet today: 'mobile' | 'home' | 'business' | 'leased' | 'none', or None."""
    s = f" {str(text).lower()} "
    if s.strip() in CURRENT_WORDS:   # tapped option
        return s.strip()
    for choice in ("leased", "home", "business", "mobile", "none"):
        if _has(s, CURRENT_WORDS[choice]):
            return choice
    return "none" if yes_no(text) is False else None

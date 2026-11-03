"""Advisor tests. These never call Groq: scripted mode, or a fake AI that returns fixed JSON."""
from datetime import date

import pytest

from backend.app.advisor.engine import Advisor
from backend.app.advisor.flow import Profile, apply_answer, next_slot
from backend.app.advisor.llm import LLMUnavailable
from backend.app.advisor.parse import number, yes_no
from backend.app.catalogue import check_bundle, load_catalogue
from backend.app.kyc.lookups import lookup_gstin, lookup_udyam, mask

TODAY = date(2026, 7, 15)


class FakeLLM:
    """Returns queued JSON answers; raises LLMUnavailable when the queue holds an exception."""
    available = True

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.tokens_used = 0

    def chat_json(self, system, messages, max_tokens=900):
        out = self.outputs.pop(0) if self.outputs else LLMUnavailable("empty")
        if isinstance(out, Exception):
            raise out
        return out


class NoLLM:
    available = False
    tokens_used = 0


# ---------- parsing ----------

@pytest.mark.parametrize("text,n", [("8 people", 8), ("हम ४ लोग", 4), ("ek hi dukaan", 1), ("आम्ही चार लोक", 4),
                                    ("just one clinic", 1), ("एकच क्लिनिक", 1), ("no idea", None)])
def test_number_words_in_three_languages(text, n):
    assert number(text) == n


@pytest.mark.parametrize("text,yn", [("haan chahiye", True), ("हो", True), ("नाही", False), ("nahi", False),
                                     ("not really", False), ("maybe later", None)])
def test_yes_no_in_three_languages(text, yn):
    assert yes_no(text) is yn


# ---------- lookups ----------

def test_gstin_lookup_statuses_and_masking():
    assert lookup_gstin("37IHKXV5167L1ZS").status == "Cancelled"           # K01
    assert lookup_gstin("27xuixg0767d1zp").active                          # K03, lower case ok
    bad = lookup_gstin("08YKZXS8189L1Z0")                                  # K06 typo
    assert not bad.format_ok and not bad.found
    assert lookup_udyam("UDYAM-MH-00-9516696").enterprise_name == "Ganesh Woodcraft"
    assert mask("37IHKXV5167L1ZS") == "37IHK******L1ZS"


# ---------- scripted flow ----------

def run_scripted(lang, answers):
    adv = Advisor(llm=NoLLM(), order_date=TODAY)
    s, out = adv.start(lang)
    for a in answers:
        out = adv.handle(s, text=a)
        if out.get("recommendation"):
            return s, out
    raise AssertionError(f"not finished, next slot {next_slot(s.profile)}")


def test_scripted_flow_gst_prefills_city_and_finishes():
    s, out = run_scripted("en", ["37IHKXV5167L1ZS", "yes", "prof", "13", "1", "fibre", "yes", "no", "yes"])
    assert s.profile.city == "Visakhapatnam" and s.profile.gstin_status == "inactive"
    ids = {x["id"] for x in out["recommendation"]["core"]}
    assert "P12" not in ids and "P09" in ids                     # telephony needs active GST; failover wanted
    assert out["recommendation"]["quote"]["valid"]


@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_scripted_flow_in_hindi_and_marathi(lang):
    s, out = run_scripted(lang, ["none", "micro", "Pune", "दो", "1", "fibre", "हो", "हो", "नाही"])  # wants WhatsApp, no GST
    rec = out["recommendation"]
    assert all(ord(c) < 128 or "ऀ" <= c <= "ॿ" or not c.isalpha() for c in rec["headline"])
    assert any("ऀ" <= c <= "ॿ" for c in rec["core"][0]["reason"])  # reasons translated
    assert any("GST" in n for n in rec["notes"])                              # WhatsApp needs GST (if offered)


def test_three_sites_turns_shop_into_multi_site():
    p = Profile()
    for slot, v in [("gstin", "none"), ("segment", "micro"), ("city", "Delhi"), ("employees", "12")]:
        apply_answer(p, slot, v)
    msgs = apply_answer(p, "sites", "4")
    assert p.segment == "multi" and msgs


def test_someone_elses_gstin_is_rejected_and_forgotten():
    p = Profile()
    apply_answer(p, "gstin", "My GST is 24XORXG9365M1Z3")      # belongs to a law firm in Vadodara
    assert next_slot(p) == "gst_confirm" and p.city == "Vadodara"
    msgs = apply_answer(p, "gst_confirm", "no")
    assert msgs and p.gstin is None and p.city is None and next_slot(p) == "gstin"


def test_bad_gstin_keeps_asking():
    p = Profile()
    assert apply_answer(p, "gstin", "12345") and p.gstin_status is None
    assert next_slot(p) == "gstin"


# ---------- AI mode with a fake model ----------

def test_ai_extract_is_validated_before_use():
    fake = FakeLLM({"extract": {"no_gstin": True, "kind": "spaceship", "city": "Pune", "employees": 99999,
                                "needs": {"backup": "yes", "teleport": True}}, "say": "Got it. How many people?"})
    adv = Advisor(llm=fake, order_date=TODAY)
    s, _ = adv.start("en")
    out = adv.handle(s, text="anything")
    p = s.profile
    assert p.gstin_status == "none" and p.city == "Pune"
    assert p.segment is None and p.employees is None          # invalid kind and absurd number rejected
    assert p.needs.backup is True and "teleport" not in p.needs_answered
    assert out["messages"] == ["What kind of business do you run?"]  # AI's question and bare "Got it." dropped
    assert out["question"]["slot"] == "segment"                                        # our order, our words


def test_ai_answers_the_confirmation_but_the_owner_decides():
    # ...and on the next turn the AI wrongly reads "no that's not us" as yes: the owner's clear "no" wins
    adv = Advisor(llm=FakeLLM({"extract": {"gst_is_theirs": True}, "say": "Okay."}), order_date=TODAY)
    s, _ = adv.start("en")
    # the AI guesses "yes, theirs" before the owner ever saw the question: must be ignored
    adv.llm.outputs.insert(0, {"extract": {"kind": "micro", "city": "Surat", "gst_is_theirs": True}, "say": ""})
    out = adv.handle(s, text="Bakery in Surat, GST is 24XORXG9365M1Z3")   # a law firm's GSTIN
    assert out["question"]["slot"] == "gst_confirm" and s.profile.segment == "micro"
    out = adv.handle(s, text="no that's not us")
    assert s.profile.gstin is None and out["question"]["slot"] == "gstin"
    assert s.profile.city == "Surat"                                     # owner's own city comes back
    assert not any("(" in m and "micro" in m for m in out["messages"])   # no internal codes leak


def test_plain_short_answers_skip_the_ai():
    fake = FakeLLM()
    adv = Advisor(llm=NoLLM(), order_date=TODAY)
    s, _ = adv.start("en")
    for a in ["none", "prof", "Pune", "8"]:
        adv.handle(s, text=a)
    adv.llm = fake
    adv.handle(s, text="just one")                       # sites
    adv.handle(s, text="fibre")                          # internet
    adv.handle(s, text="nahi")                           # phone system
    assert s.profile.sites == 1 and s.profile.needs.phone_system is False and not s.fallbacks


def test_ai_failure_falls_back_to_scripted_without_error():
    adv = Advisor(llm=FakeLLM(LLMUnavailable("RateLimitError")), order_date=TODAY)
    s, _ = adv.start("en")
    out = adv.handle(s, text="I don't have GST, no")
    assert s.profile.gstin_status == "none"                    # scripted path understood it
    assert out["question"]["slot"] == "segment"
    assert s.fallbacks == ["turn:RateLimitError"]


def test_safety_net_records_plain_answers_the_ai_missed():
    p_answers = ["none", "prof", "Pune", "8", "1", "fibre"]
    adv = Advisor(llm=NoLLM(), order_date=TODAY)
    s, _ = adv.start("en")
    for a in p_answers:
        adv.handle(s, text=a)
    assert next_slot(s.profile) == "need:phone_system"
    adv.llm = FakeLLM({"extract": {}, "say": "Do you keep client files?"})
    adv.handle(s, text="haan ji, hamein chahiye bilkul")      # long enough to go to the AI, which misses it
    assert s.profile.needs.phone_system is True and "safety_net:need:phone_system" in s.fallbacks


def test_ai_explanation_cannot_drop_products_or_notes():
    answers = ["none", "micro", "Pune", "3", "1", "fibre", "yes", "yes", "no"]
    adv = Advisor(llm=NoLLM(), order_date=TODAY)
    s, _ = adv.start("en")
    for a in answers[:-1]:
        adv.handle(s, text=a)
    adv.llm = FakeLLM({"summary": "Great fit.", "reasons": {"P01": "Fast fibre."}, "notes": []})
    out = adv.handle(s, text="no")                     # plain "no": parser handles it, AI only explains
    rec = out["recommendation"]
    assert rec["summary"] == "Great fit."
    assert rec["core"][0]["reason"] == "Fast fibre."
    assert all(item["reason"] for item in rec["core"] + rec["addons"])   # template fills products AI skipped
    assert rec["notes"]                                                  # AI dropped notes -> template kept
    items = {x["id"]: x["quantity"] for x in rec["core"]}
    assert all(c.ok for c in check_bundle(items, adv_business(s)).values())


def adv_business(s):
    from backend.app.advisor.flow import to_business
    return to_business(s.profile)


def test_reason_exists_for_every_product_in_every_language():
    import json
    from pathlib import Path
    for lang in ("en", "hi", "mr"):
        strings = json.loads((Path("backend/app/i18n") / f"{lang}.json").read_text(encoding="utf-8"))
        assert all(f"reason.{pid}" in strings for pid in load_catalogue())


@pytest.mark.parametrize("typed,city,tier", [("पुणे", "Pune", 1), ("bombay", "Mumbai", 1), ("नागपूर", "Nagpur", 2),
                                             ("Satara", "Satara", 2)])
def test_city_names_in_any_script_get_the_right_tier(typed, city, tier):
    from backend.app.advisor.flow import set_city
    p = Profile()
    set_city(p, typed)
    assert (p.city, p.city_tier) == (city, tier)


def test_unclear_answer_repeats_the_question_only_once():
    adv = Advisor(llm=NoLLM(), order_date=TODAY)
    s, _ = adv.start("en")
    for a in ["none", "prof", "Pune", "8", "1", "fibre"]:
        adv.handle(s, text=a)
    out = adv.handle(s, text="what is that?")
    assert out["messages"] == ["Please answer yes or no.", "Do you need business phone lines with a welcome menu for callers?"]


def test_typed_answers_work_without_ai():
    """If the AI is down, typed words still move the chat on: kind of business, city in a sentence, number words."""
    adv = Advisor(llm=NoLLM(), order_date=TODAY)
    s, _ = adv.start("en")
    out = adv.handle(s, text="03PJNXS4821G1ZB")
    assert "Please answer" not in " ".join(out["messages"])     # the GSTIN is not taken as the yes/no answer
    for a in ["no, not us", "skip, no GST", "kapdon ki 6 dukaanein hain", "We are in Chennai", "about twenty five"]:
        adv.handle(s, text=a)
    p = s.profile
    assert (p.gstin_status, p.segment, p.city, p.employees) == ("none", "multi", "Chennai", 25)


def test_kind_of_business_and_city_readers():
    from backend.app.advisor.parse import kind_of_business
    from backend.app.reference import find_city
    cases = {"kirana store": "micro", "मेरी दवाई की दुकान है": "micro", "माझं सलून आहे": "micro", "law firm": "prof",
             "कोचिंग सेंटर": "prof", "restaurant chain": "multi", "कापड कारखाना": "mfg", "packaging factory": "mfg",
             "what's the weather?": None}
    assert {k: kind_of_business(k) for k in cases} == cases
    assert find_city("we are based in poona") == "Pune" and find_city("हम नाशिक में हैं") == "Nashik"
    assert find_city("Sangli") == "Sangli" and find_city("what is SD-WAN?") is None


# ---------- internet question: fibre, 5G wireless, not sure, mobile only ----------

def test_mobile_only_owner_gets_no_internet_line_and_no_internet_questions():
    adv = Advisor(llm=NoLLM(), order_date=TODAY)
    s, _ = adv.start("en")
    asked = []
    out = {}
    for a in ["none", "micro", "Pune", "3", "1", "sirf mobile sim chahiye", "no", "no", "no"]:
        out = adv.handle(s, text=a)
        if out.get("question"):
            asked.append(out["question"]["slot"])
        if out.get("recommendation"):
            break
    rec = out["recommendation"]
    core = {x["id"] for x in rec["core"]}
    assert "need:cctv" not in asked                                  # cameras need an internet line
    assert core == {"P07"} and rec["quote"]["valid"] and not rec["notes"]
    assert all(not load_catalogue()[x["id"]].requires_one_of for x in rec["addons"])


@pytest.mark.parametrize("typed,line", [("no fibre here", "P04"), ("5G wireless", "P04"), ("fibre", "P01"),
                                        ("पता नहीं", "P01")])
def test_internet_answer_picks_the_line(typed, line):
    s, out = run_scripted("en", ["none", "micro", "Pune", "3", "1", typed, "no", "no", "no"])
    assert out["recommendation"]["core"][0]["id"] == line


def test_not_sure_about_fibre_is_explained():
    adv = Advisor(llm=NoLLM(), order_date=TODAY)
    s, _ = adv.start("en")
    for a in ["none", "micro", "Pune", "3", "1"]:
        adv.handle(s, text=a)
    out = adv.handle(s, text="not sure")
    assert any("5G AirFiber instead" in m for m in out["messages"])


# ---------- privacy: what the chat AI receives ----------

class RecordingLLM(FakeLLM):
    def __init__(self):
        super().__init__()
        self.sent = []

    def chat_json(self, system, messages, max_tokens=900):
        self.sent.append(messages)
        return {"extract": {}, "say": ""}


def test_ai_never_gets_ids_business_name_or_chat_history():
    llm = RecordingLLM()
    adv = Advisor(llm=llm, order_date=TODAY)
    s, start = adv.start("en")
    assert any("AI service" in m for m in start["messages"])          # owner is told an AI reads replies
    adv.handle(s, text="my GST is 27XUIXG0767D1ZP and we make furniture, call me on 9876543210")
    adv.handle(s, text="yes that is Ganesh Woodcraft, our business")
    adv.handle(s, text="we are a small furniture factory with udyam UDYAM-MH-00-1234567")
    assert len(llm.sent) == 3
    for messages in llm.sent:
        assert len(messages) == 1                                      # current message only, no history
        sent = str(messages)
        for secret in ("27XUIXG0767D1ZP", "27XUI", "9876543210", "UDYAM-MH", "Ganesh Woodcraft"):
            assert secret not in sent, secret
    assert s.profile.gstin == "27XUIXG0767D1ZP"                       # our own code still read the GST number


def test_no_ai_notice_when_the_ai_is_off():
    _, start = Advisor(llm=NoLLM(), order_date=TODAY).start("en")
    assert not any("AI service" in m for m in start["messages"])

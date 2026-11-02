"""Run owner personas through the advisor and check every conversation, the way judges test it live.

Each persona answers whatever question is on screen in its own free-text words (no button taps).
Checks per conversation:
  - it finishes within MAX_TURNS and never asks the same question 3 times in a row
  - the bundle passes every catalogue rule and the quote is valid
  - every need the owner said yes to is in the bundle or explained in a note; no product they said no to
  - expected facts (kind of business, city, staff, sites, GST status) were understood
  - bot text is in the owner's language and never shows product codes or field names

Usage: .venv/Scripts/python scripts/eval_advisor.py [scripted|ai] [persona names...]
AI mode is paced for the Groq free tier (8K tokens/minute); each conversation uses about 4-5K tokens.
Set PYTHONIOENCODING=utf-8 on Windows.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.app.advisor.engine import Advisor  # noqa: E402
from backend.app.advisor.flow import NEED_QUESTIONS, to_business  # noqa: E402
from backend.app.catalogue import check_bundle  # noqa: E402
from backend.app.recommend import NEED_PRODUCT  # noqa: E402

MAX_TURNS = 14
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LEAKS = re.compile(r"\bP\d{2}\b|need:|[{}]|\b[a-z]+_[a-z_]+\b|\bNone\b|\bnull\b")

# answers: slot -> reply (a list = replies for repeated asks, the last one repeats). Missing need slots -> "no".
PERSONAS = [
    dict(name="kirana_indore_en", lang="en",
         answers={"gstin": "no GST yet", "segment": "I run a kirana store", "city": "Indore",
                  "employees": "3 of us, me and 2 helpers", "sites": "just one shop",
                  "need:billing_pos": "yes, lots of customers pay by UPI", "need:whatsapp": "yes please",
                  "need:cctv": "not needed"},
         expect=dict(segment="micro", city="Indore", employees=3, sites=1, gstin_status="none")),
    dict(name="medical_lucknow_hi", lang="hi",
         answers={"gstin": "जीएसटी नहीं है", "segment": "मेरी दवाई की दुकान है", "city": "लखनऊ",
                  "employees": "३ लोग", "sites": "एक दुकान", "need:billing_pos": "हाँ, UPI से पेमेंट लेते हैं",
                  "need:whatsapp": "नहीं", "need:cctv": "हाँ चाहिए"},
         expect=dict(segment="micro", city="Lucknow", employees=3, sites=1, gstin_status="none")),
    dict(name="salon_nashik_mr", lang="mr",
         answers={"gstin": "GST नाही", "segment": "माझं सलून आहे", "city": "नाशिक", "employees": "दोन",
                  "sites": "एकच", "need:billing_pos": "हो", "need:whatsapp": "हो", "need:cctv": "नाही"},
         expect=dict(segment="micro", city="Nashik", employees=2, sites=1, gstin_status="none")),
    dict(name="parlour_hinglish", lang="en",
         answers={"gstin": "bhai GST nahi hai", "segment": "beauty parlour hai", "city": "Jaipur",
                  "employees": "4 ladkiyan kaam karti hain", "sites": "ek hi parlour",
                  "need:billing_pos": "haan UPI chahiye", "need:whatsapp": "haan", "need:cctv": "nahi"},
         expect=dict(segment="micro", city="Jaipur", employees=4, sites=1, gstin_status="none")),
    dict(name="law_office_pune_gst", lang="en",
         answers={"gstin": "27DGKXS9651J1Z2", "gst_confirm": "yes that's us", "segment": "we are a law firm",
                  "employees": "8", "sites": "one office", "need:phone_system": "yes we get many client calls",
                  "need:backup": "yes, client files are important", "need:failover": "no"},
         expect=dict(segment="prof", city="Pune", employees=8, sites=1, gstin_status="active")),
    dict(name="pharmacy_mumbai_gst_hi", lang="hi",
         answers={"gstin": "हमारा GST 27UOIXN0412X1ZA है", "gst_confirm": "हाँ", "segment": "फार्मेसी",
                  "employees": "5", "sites": "1", "need:billing_pos": "हाँ", "need:whatsapp": "हाँ",
                  "need:cctv": "हाँ"},
         expect=dict(segment="micro", city="Mumbai", employees=5, sites=1, gstin_status="active")),
    dict(name="gst_not_ours", lang="en",
         answers={"gstin": ["03PJNXS4821G1ZB", "we don't have GST actually"], "gst_confirm": "no, that's not us",
                  "segment": "bakery", "city": "Chandigarh", "employees": "3", "sites": "1",
                  "need:billing_pos": "yes", "need:whatsapp": "yes", "need:cctv": "no"},
         expect=dict(segment="micro", city="Chandigarh", gstin_status="none")),
    dict(name="cancelled_gst_store", lang="en",
         answers={"gstin": "29OKAXP4077P1ZL", "gst_confirm": "yes", "segment": "general store",
                  "employees": "2", "sites": "1", "need:billing_pos": "yes", "need:whatsapp": "no",
                  "need:cctv": "yes"},
         expect=dict(segment="micro", city="Bengaluru", gstin_status="inactive")),
    dict(name="suspended_gst_factory", lang="en",
         answers={"gstin": "27KYVXC5489I1ZX", "gst_confirm": "yes", "segment": "packaging factory",
                  "employees": "40", "sites": "1", "need:machines": "12", "need:vehicles": "3",
                  "need:firewall": "yes"},
         expect=dict(segment="mfg", city="Mumbai", employees=40, gstin_status="inactive")),
    dict(name="typo_gstin_then_none", lang="en",
         answers={"gstin": ["27ABCDE1234F1Z5", "skip it, no GST"], "segment": "tailoring shop",
                  "city": "Surat", "employees": "1", "sites": "1"},
         expect=dict(segment="micro", city="Surat", employees=1, gstin_status="none")),
    dict(name="restaurant_chain_hyd", lang="en",
         answers={"gstin": "don't have it handy", "segment": "restaurant chain", "city": "Hyderabad",
                  "employees": "35", "sites": "4 outlets", "need:central_management": "yes",
                  "need:cctv": "yes in all outlets", "need:toll_free": "yes for orders"},
         expect=dict(segment="multi", city="Hyderabad", employees=35, sites=4)),
    dict(name="retail_chain_jaipur_hinglish", lang="hi",
         answers={"gstin": "abhi nahi hai", "segment": "kapdon ki 6 dukaanein hain", "city": "jaipur",
                  "employees": "25 log", "sites": "6", "need:central_management": "haan",
                  "need:cctv": "haan", "need:toll_free": "nahi"},
         expect=dict(segment="multi", city="Jaipur", sites=6)),
    dict(name="autoparts_ludhiana", lang="en",
         answers={"gstin": "no", "segment": "auto parts manufacturing unit", "city": "Ludhiana",
                  "employees": "25", "sites": "1", "need:machines": "6 CNC machines", "need:vehicles": "3 trucks",
                  "need:firewall": "yes"},
         expect=dict(segment="mfg", city="Ludhiana", employees=25, sites=1)),
    dict(name="textile_surat_mr", lang="mr",
         answers={"gstin": "नाही", "segment": "कापड कारखाना", "city": "सूरत", "employees": "६०",
                  "sites": "२", "need:machines": "१०", "need:vehicles": "०", "need:firewall": "हो"},
         expect=dict(segment="mfg", city="Surat", employees=60, sites=2)),
    dict(name="asks_question_midway", lang="en",
         answers={"gstin": "none", "segment": "mobile repair shop", "city": "Pune", "employees": "2",
                  "sites": "1", "need:billing_pos": "yes",
                  "need:whatsapp": ["what does the WhatsApp product do?", "ok yes"],
                  "need:cctv": ["is CCTV recording stored online?", "no thanks"]},
         expect=dict(segment="micro", city="Pune", employees=2, sites=1)),
    dict(name="micro_becomes_multi", lang="en",
         answers={"gstin": "no", "segment": "sweet shop", "city": "Nagpur", "employees": "12",
                  "sites": "we have 4 shops", "need:central_management": "yes", "need:cctv": "yes",
                  "need:toll_free": "no"},
         expect=dict(segment="multi", city="Nagpur", sites=4)),
    dict(name="all_in_first_message", lang="en",
         answers={"gstin": "No GST. I run a coaching centre in Delhi with 12 teachers, one branch.",
                  "segment": "coaching centre", "city": "Delhi", "employees": "12", "sites": "1",
                  "need:phone_system": "no", "need:backup": "yes", "need:failover": "yes"},
         expect=dict(segment="prof", city="Delhi", employees=[12, 13], sites=1, gstin_status="none")),
    dict(name="unknown_small_town", lang="en",
         answers={"gstin": "no", "segment": "hardware shop", "city": "Sangli", "employees": "3",
                  "sites": "1", "need:billing_pos": "yes", "need:whatsapp": "no", "need:cctv": "yes"},
         expect=dict(segment="micro", city="Sangli", sites=1)),
    dict(name="noise_and_odd_numbers", lang="en",
         answers={"gstin": ["asdf", "no gst"], "segment": ["what's the weather?", "clinic"],
                  "city": "We are in Chennai", "employees": ["many", "about twenty five"],
                  "sites": ["0", "1"], "need:phone_system": ["maybe", "no"], "need:backup": "yes", "need:failover": "no"},
         expect=dict(segment="prof", city="Chennai", sites=1)),
    dict(name="coaching_patna_hi", lang="hi",
         answers={"gstin": "नहीं", "segment": "कोचिंग सेंटर", "city": "पटना", "employees": "१५",
                  "sites": "१", "need:phone_system": "हाँ", "need:backup": "नहीं", "need:failover": "हाँ"},
         expect=dict(segment="prof", city="Patna", employees=15, sites=1)),
]


class NoLLM:
    available = False
    tokens_used = 0


def reply_for(persona: dict, slot: str, asked: dict) -> str:
    ans = persona["answers"].get(slot, "no")
    if isinstance(ans, list):
        i = asked.get(slot, 0)
        ans = ans[min(i, len(ans) - 1)]
    asked[slot] = asked.get(slot, 0) + 1
    return ans


def bot_texts(out: dict) -> list[str]:
    texts = list(out.get("messages", []))
    rec = out.get("recommendation")
    if rec:
        texts += [rec.get("summary") or "", *rec["notes"], *(x["reason"] for x in rec["core"] + rec["addons"])]
    return [x for x in texts if x]


def language_ok(text: str, lang: str) -> bool:
    if lang == "en":
        return not DEVANAGARI.search(text)
    return bool(DEVANAGARI.search(text))


def run(persona: dict, adv: Advisor) -> dict:
    session, out = adv.start(persona["lang"])
    problems, transcript, asked, turns, last_slot, streak = [], [], {}, 0, None, 0
    all_bot = list(out["messages"])
    transcript += [f"BOT: {m}" for m in out["messages"]]
    while out.get("question") and turns < MAX_TURNS:
        slot = out["question"]["slot"]
        streak = streak + 1 if slot == last_slot else 1
        last_slot = slot
        if streak >= 3:
            problems.append(f"asked '{slot}' 3 times in a row")
            break
        text = reply_for(persona, slot, asked)
        out = adv.handle(session, text=text)
        turns += 1
        transcript.append(f"YOU [{slot}]: {text}")
        transcript += [f"BOT: {m}" for m in out["messages"]]
        all_bot += bot_texts(out)
    p = session.profile
    rec = session.recommendation
    if rec is None:
        problems.append(f"did not finish in {turns} turns (stuck on {out.get('question', {}).get('slot')})")
    else:
        biz = to_business(p)
        bad = {pid: c.reasons for pid, c in check_bundle(rec.items(), biz).items() if not c.ok}
        if bad:
            problems.append(f"rule breaks: {bad}")
        if not rec.quote.valid:
            problems.append("quote not valid")
        core = set(rec.items())
        explained = {n.get("product") for n in rec.note_items} | {n.get("alt") for n in rec.note_items}
        for need in NEED_QUESTIONS.get(p.segment, []):
            pid = NEED_PRODUCT.get(need)
            val = getattr(p.needs, need, None)
            if pid and val is True and pid not in core and pid not in explained:
                problems.append(f"said yes to {need} but {pid} missing and not explained")
            if pid and val is False and pid in core:
                problems.append(f"said no to {need} but {pid} included")
        for key, want in [("machines", "P24"), ("vehicles", "P25")]:
            if getattr(p.needs, key) and want not in core and want not in explained:
                problems.append(f"{key}={getattr(p.needs, key)} but {want} missing")
    for key, want in persona.get("expect", {}).items():
        got = getattr(p, key)
        if got != want and not (isinstance(want, list) and got in want):
            problems.append(f"{key}: expected {want!r}, got {got!r}")
    for text in all_bot:
        if LEAKS.search(text):
            problems.append(f"leak: {LEAKS.search(text).group(0)!r} in {text[:80]!r}")
        if not language_ok(text, persona["lang"]):
            problems.append(f"wrong language: {text[:80]!r}")
    return {"name": persona["name"], "ok": not problems, "turns": turns, "problems": problems,
            "items": rec.items() if rec else None, "fallbacks": session.fallbacks, "transcript": transcript}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "scripted"
    names = set(sys.argv[2:])
    personas = [x for x in PERSONAS if not names or x["name"] in names]
    results = []
    for i, persona in enumerate(personas):
        adv = Advisor(llm=NoLLM() if mode == "scripted" else None, order_date=date(2026, 7, 15))
        if mode == "ai" and not adv.llm.available:
            sys.exit("AI mode needs GROQ_API_KEY in .env")
        t0 = time.time()
        r = run(persona, adv)
        r["seconds"], r["tokens"] = round(time.time() - t0, 1), adv.llm.tokens_used
        results.append(r)
        flag = "PASS" if r["ok"] else "FAIL"
        print(f"{flag} {r['name']:<30} turns={r['turns']:<2} tokens={r['tokens']:<5} {r['seconds']}s "
              f"items={r['items']} fallbacks={r['fallbacks']}")
        for prob in r["problems"]:
            print("     -", prob)
        if mode == "ai" and i < len(personas) - 1:
            time.sleep(max(0, r["tokens"] / 7000 * 60 - r["seconds"]))  # stay under 8K tokens/minute
    out = ROOT / "analysis" / f"eval_advisor_{mode}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{sum(r['ok'] for r in results)}/{len(results)} passed, "
          f"{sum(r['tokens'] for r in results)} tokens -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

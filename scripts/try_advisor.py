"""Play a free-text conversation through the advisor and print each turn.

Usage: .venv/Scripts/python scripts/try_advisor.py <language> "<msg 1>" "<msg 2>" ...
Set PYTHONIOENCODING=utf-8 on Windows to print Hindi/Marathi.
"""
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app.advisor.engine import Advisor  # noqa: E402

lang, messages = sys.argv[1], sys.argv[2:]
adv = Advisor(order_date=date(2026, 7, 15))
session, out = adv.start(lang)
print(f"[mode={out['mode']}]")
for m in out["messages"]:
    print("BOT :", m)
for text in messages:
    t0 = time.time()
    out = adv.handle(session, text=text)
    print(f"\nYOU : {text}   ({time.time() - t0:.1f}s, tokens so far {adv.llm.tokens_used})")
    for m in out["messages"]:
        print("BOT :", m)
    if out.get("recommendation"):
        r = out["recommendation"]
        if r.get("summary"):
            print("SUMMARY:", r["summary"])
        for item in r["core"]:
            print(f"  + {item['id']} x{item['quantity']}: {item['reason']}")
        for item in r["addons"]:
            print(f"  ? {item['id']} x{item['quantity']}: {item['reason']}")
        for n in r["notes"]:
            print("  note:", n)
        q = r["quote"]
        print(f"  TOTAL Rs{q['monthly_total']} + GST {q['monthly_gst']} = Rs{q['monthly_with_gst']}/month, "
              f"setup Rs{q['setup_total']}, {q['contract_months']} months, live by {q['expected_live']}")
        break
print("\nprofile:", session.profile.safe_view())
print("fallbacks:", session.fallbacks, "| total tokens:", adv.llm.tokens_used)

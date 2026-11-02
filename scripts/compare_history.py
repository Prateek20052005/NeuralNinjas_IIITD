"""Compare the recommender with what the 368 activated customers actually bought.

Measures, per segment:
  overlap  - share of the customer's products that we also put in core or add-ons (recall)
  core_hit - share of our core products the customer actually bought (precision)
  price    - our core monthly price vs what they paid
Usage: .venv/Scripts/python scripts/compare_history.py
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app.catalogue import DATA_DIR, Business  # noqa: E402
from backend.app.recommend import recommend  # noqa: E402
from backend.app.reference import SEGMENT_CODE  # noqa: E402

leads = pd.read_csv(DATA_DIR / "smb_leads.csv")
reg = pd.read_csv(DATA_DIR / "mock_gstin_registry.csv").set_index("gstin").status
act = leads[leads.outcome == "Activated"]

rows = []
for _, r in act.iterrows():
    status = "none" if pd.isna(r.gstin) else ("active" if reg[r.gstin] == "Active" else "inactive")
    b = Business(SEGMENT_CODE[r.segment], int(r.city_tier), int(r.employee_count), int(r.num_sites), status)
    rec = recommend(b, order_date=date(2026, 7, 15))
    bought = {x.split("x")[0] for x in r.bundle_products.split(";")}
    core = set(rec.items())
    offered = core | {a.product_id for a in rec.addons}
    rows.append({"segment": r.segment, "overlap": len(bought & offered) / len(bought),
                 "core_hit": len(bought & core) / len(core), "ours": rec.quote.monthly_total,
                 "paid": r.monthly_bundle_value_inr})

df = pd.DataFrame(rows)
summary = df.groupby("segment").agg(n=("overlap", "size"), overlap=("overlap", "mean"), core_hit=("core_hit", "mean"),
                                    our_median=("ours", "median"), paid_median=("paid", "median"))
summary.loc["ALL"] = [len(df), df.overlap.mean(), df.core_hit.mean(), df.ours.median(), df.paid.median()]
print(summary.round(2).to_string())

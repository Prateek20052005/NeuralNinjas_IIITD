"""What sells together: Apriori-style association rules, learned separately for each kind of business.

Learned from the bundles the 368 activated customers in smb_leads.csv actually bought. Rules are kept per kind of
business because across all businesses most "bought together" pairs only reflect the kind of business (offices buy
more of everything); within a kind, a rule says something real ("offices with Endpoint Security also took Cloud
Backup 57% of the time").

A rule A -> B counts only with enough evidence: at least MIN_WITH customers had A, at least MIN_BOTH had both, and
having A makes B at least MIN_LIFT times as likely as it is for that kind of business overall (lift).

Used to order a plan's optional extras (most likely first) and to show a short, true line under each one
("38% of similar businesses chose this"). It never adds a product or changes a price: the catalogue rules decide
what can be offered, this only decides the order and the words.
"""
from __future__ import annotations

import csv
import itertools
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from .catalogue import DATA_DIR, SEGMENTS, load_catalogue

MIN_WITH = 10        # customers who had the "if" product
MIN_BOTH = 5         # customers who had both
MIN_LIFT = 1.2       # the "if" product must make the extra at least this much more likely
SHOW_FROM_PCT = 15   # below this, a "chose this" line would say little: none is shown

_CODE = {name: code for code, name in SEGMENTS.items()}


@dataclass(frozen=True)
class Kind:
    customers: int
    has: Counter          # product -> customers who bought it
    pairs: Counter        # (a, b) -> customers who bought both


@lru_cache(maxsize=1)
def _by_kind() -> dict[str, Kind]:
    bundles: dict[str, list[set[str]]] = {}
    with open(DATA_DIR / "smb_leads.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["outcome"] == "Activated" and r["bundle_products"]:
                bundles.setdefault(_CODE[r["segment"]], []).append(
                    {item.split("x")[0] for item in r["bundle_products"].split(";")})
    return {kind: Kind(len(bs), Counter(p for b in bs for p in b),
                       Counter(pair for b in bs for pair in itertools.permutations(sorted(b), 2)))
            for kind, bs in bundles.items()}


def likelihood(kind: str, have: set[str], pid: str, near: list | None = None) -> dict | None:
    """How often similar businesses took `pid`: the strongest rule from a product already in the plan, else the share
    among the most similar past customers (similar.py) when given, else of that kind of business overall.
    None when there is no data for this kind."""
    k = _by_kind().get(kind)
    if not k or not k.customers:
        return None
    share = k.has[pid] / k.customers
    base = sum(pid in c.items for c in near) / len(near) if near else share
    best = {"pct": round(100 * base), "with": None, "lift": 1.0}
    for a in have - {pid}:
        if k.has[a] >= MIN_WITH and k.pairs[(a, pid)] >= MIN_BOTH and share:
            conf = k.pairs[(a, pid)] / k.has[a]
            if conf / share >= MIN_LIFT and round(100 * conf) > best["pct"]:
                best = {"pct": round(100 * conf), "with": a, "lift": round(conf / share, 2)}
    return best


def rank_extras(kind: str, have: set[str], extras: list[str], near: list | None = None) -> list[tuple[str, dict | None]]:
    """The extras, most likely first (ties keep the plan's own order), each with its likelihood."""
    scored = [(pid, likelihood(kind, have, pid, near)) for pid in extras]
    return sorted(scored, key=lambda s: -(s[1]["pct"] if s[1] else 0))


def top_rules(per_kind: int = 3) -> list[dict]:
    """The strongest 'bought together' rules for each kind of business (for the back office)."""
    names, out = load_catalogue(), []
    for kind, k in sorted(_by_kind().items()):
        rules = []
        for (a, b), both in k.pairs.items():
            if k.has[a] >= MIN_WITH and both >= MIN_BOTH:
                conf, share = both / k.has[a], k.has[b] / k.customers
                if conf / share >= MIN_LIFT:
                    rules.append({"kind": kind, "if": names[a].name, "then": names[b].name, "customers": k.has[a],
                                  "pct": round(100 * conf), "usual_pct": round(100 * share),
                                  "lift": round(conf / share, 2)})
        # a pair and its reverse say the same thing: keep the direction with the higher share, once
        kept, seen = [], set()
        for r in sorted(rules, key=lambda r: (-r["lift"], -r["pct"], -r["customers"])):
            pair = frozenset((r["if"], r["then"]))
            if pair not in seen:
                seen.add(pair)
                kept.append(r)
        out += kept[:per_kind]
    return out

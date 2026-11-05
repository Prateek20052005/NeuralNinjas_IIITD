"""Conversion predictor: how likely is a lead (or a live application) to end up activated?

A logistic regression trained on the 5,000 historical leads in smb_leads.csv, using only what is known when a lead
comes in: source, kind of business, city tier, size, turnover, current internet and provider, monthly telecom spend,
GST and Udyam registration, and how many products they asked about. Nothing that happens later (stages, dates, drop
reasons) is used, so the score is not cheating. The owner's language is left out on purpose: the app exists to serve
owners in their own language, and a score that ranks them by it would work against that.

Scores are probabilities from past results (7.8% of leads activated). They rank who to call first; they never
decide anything for an owner. Plain numpy, so no extra library is needed.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .catalogue import DATA_DIR, SEGMENTS

CATEGORIES = ["lead_source", "segment", "city_tier", "current_internet", "current_provider", "annual_turnover_band",
              "has_gstin", "has_udyam"]
NUMBERS = ["employees", "sites", "spend", "interests"]

# plain words for the reasons shown to sales staff
LABELS = {
    ("has_gstin", "Y"): "has GST", ("has_gstin", "N"): "no GST",
    ("has_udyam", "Y"): "has Udyam", ("has_udyam", "N"): "no Udyam",
    ("city_tier", "1"): "tier-1 city", ("city_tier", "2"): "tier-2 city",
    ("annual_turnover_band", "< 40 lakh"): "turnover under 40 lakh",
}
SIZES = {"employees": ("bigger team", "smaller team"), "sites": ("more sites", "fewer sites"),
         "spend": ("higher telecom spend", "lower telecom spend"),
         "interests": ("asked about more products", "asked about fewer products")}
# drop reasons the new app answers, so these leads are worth another try (and what changed for them)
WORTH_RETRYING = {
    "Owner had no time for a visit": "No visit needed: the chat takes a few minutes",
    "Visit not scheduled by sales": "No visit needed: the chat takes a few minutes",
    "Quote took too long to arrive": "Quote in minutes in the chat",
    "Quote too complex to understand": "One clear monthly price, in their language",
    "Price too high": "Basic plan, longer contracts and the new-customer offer",
    "Only wanted a mobile plan": "Mobile-only plans now offered",
    "Missing GST or Udyam document": "No GST needed: address proof and ID only",
    "Found paperwork too long": "Photos read on the spot, no paperwork",
    "Decided to wait": "Save progress and continue later",
    "Unreachable after 3 attempts": "Self-serve link instead of calls",
}


def _label(name: str, level: str | None = None, value: float = 0.0) -> str:
    if level is None:   # a number: say which way this lead differs from the average
        return SIZES[name][0 if value > 0 else 1]
    if (name, level) in LABELS:
        return LABELS[(name, level)]
    return {"lead_source": f"came via {level.lower()}", "segment": level.lower(),
            "current_internet": f"uses {level.lower()}", "current_provider": f"with {level}"}.get(name, f"{name}: {level}")


def lead_features(r: dict) -> dict:
    """The predictor's inputs from a leads-file row. Missing values stay None (scored as average)."""
    interests = [p for p in (r.get("products_of_interest") or "").split(";") if p]
    return {**{c: r.get(c) or None for c in CATEGORIES},
            "employees": int(r["employee_count"]) if r.get("employee_count") else None,
            "sites": int(r["num_sites"]) if r.get("num_sites") else None,
            "spend": float(r["monthly_telecom_spend_inr"]) if r.get("monthly_telecom_spend_inr") else None,
            "interests": len(interests) if r.get("products_of_interest") is not None else None}


@dataclass
class Model:
    levels: dict[str, list[str]]
    mean: np.ndarray
    scale: np.ndarray
    weights: np.ndarray            # [bias, ...features]
    names: list[tuple[str, str | None]]
    metrics: dict

    def vector(self, f: dict) -> np.ndarray:
        """Unknown values are set to the training average, so they push the score neither way."""
        raw = []
        for c in CATEGORIES:
            raw += [float(f.get(c) == lv) if f.get(c) is not None else None for lv in self.levels[c][1:]]
        nums = {"employees": f.get("employees"), "sites": f.get("sites"), "spend": f.get("spend"),
                "interests": f.get("interests")}
        raw += [None if nums[n] is None else (math.log1p(nums[n]) if n != "interests" else float(nums[n])) for n in NUMBERS]
        x = np.array([self.mean[i] if v is None else v for i, v in enumerate(raw)])
        return (x - self.mean) / self.scale

    def score(self, f: dict) -> tuple[float, list[str], list[str]]:
        """(probability of activation, what raises it, what lowers it), in plain words.
        Reasons only name things that are true of this lead (never "is not an office")."""
        z = self.vector(f)
        p = 1 / (1 + math.exp(-(self.weights[0] + z @ self.weights[1:])))
        parts = z * self.weights[1:]
        true_of_lead = [level is None or f.get(name) == level for name, level in self.names]

        def why(i):
            name, level = self.names[i]
            return _label(name, level, z[i])
        up = [why(i) for i in np.argsort(-parts) if parts[i] > 0.05 and true_of_lead[i]][:3]
        down = [why(i) for i in np.argsort(parts) if parts[i] < -0.05 and true_of_lead[i]][:2]
        return round(float(p), 3), up, down


def _rows() -> list[dict]:
    with open(DATA_DIR / "smb_leads.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _fit(x: np.ndarray, y: np.ndarray, steps: int = 3000, l2: float = 0.01) -> np.ndarray:
    x = np.c_[np.ones(len(x)), x]
    w = np.zeros(x.shape[1])
    for _ in range(steps):
        p = 1 / (1 + np.exp(-x @ w))
        w -= 0.5 * (x.T @ (p - y) / len(y) + l2 * np.r_[0, w[1:]])
    return w


def _auc(score: np.ndarray, truth: np.ndarray) -> float:
    rank = np.empty(len(score))
    rank[np.argsort(score)] = np.arange(1, len(score) + 1)
    pos, neg = truth.sum(), len(truth) - truth.sum()
    return float((rank[truth == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


@lru_cache(maxsize=1)
def model() -> Model:
    rows = _rows()
    levels = {c: sorted({r[c] for r in rows}) for c in CATEGORIES}
    names = [(c, lv) for c in CATEGORIES for lv in levels[c][1:]] + [(n, None) for n in NUMBERS]
    shell = Model(levels, np.zeros(len(names)), np.ones(len(names)), np.zeros(len(names) + 1), names, {})
    x = np.array([shell.vector(lead_features(r)) for r in rows])     # raw values (mean 0, scale 1 for now)
    y = np.array([r["outcome"] == "Activated" for r in rows], dtype=float)
    mean, scale = x.mean(0), x.std(0) + 1e-9
    xs = (x - mean) / scale

    # honest accuracy: train on 80%, measure on the 20% it never saw; then train on everything for use
    order = np.random.default_rng(7).permutation(len(y))
    train, test = order[: int(0.8 * len(y))], order[int(0.8 * len(y)):]
    w = _fit(xs[train], y[train])
    p_test = 1 / (1 + np.exp(-(w[0] + xs[test] @ w[1:])))
    top = np.argsort(-p_test)[: max(1, len(test) // 10)]
    metrics = {"leads": len(y), "activated_pct": round(float(100 * y.mean()), 1), "test_leads": len(test),
               "auc": round(_auc(p_test, y[test]), 3), "top10_activated_pct": round(float(100 * y[test][top].mean()), 1),
               "base_activated_pct": round(float(100 * y[test].mean()), 1),
               "features": ["lead source", "kind of business", "city tier", "current internet", "current provider",
                            "turnover", "GST", "Udyam", "team size", "sites", "telecom spend", "products asked about"],
               "left_out": ["language (fairness)", "stages, dates and drop reasons (only known later)"]}
    final = Model(levels, mean, scale, _fit(xs, y), names, metrics)
    weights = final.weights[1:]
    final.metrics["strongest"] = [{"factor": _label(names[i][0], names[i][1], 1.0), "effect": "raises" if weights[i] > 0 else "lowers"}
                                  for i in np.argsort(-np.abs(weights))[:6]]
    return final


def leads_to_call(limit: int = 50) -> list[dict]:
    """Past leads that dropped for a reason the new app now answers, best chance first."""
    m, out = model(), []
    for r in _rows():
        if r["outcome"] != "Dropped" or r["drop_reason"] not in WORTH_RETRYING:
            continue
        p, up, down = m.score(lead_features(r))
        out.append({"lead_id": r["lead_id"], "business": r["business_name"], "type": r["business_type"],
                    "city": r["city"], "segment": r["segment"], "source": r["lead_source"],
                    "contact": f"{r['contact_name']} ({r['contact_role']})", "stage": r["stage_reached"],
                    "drop_reason": r["drop_reason"], "now": WORTH_RETRYING[r["drop_reason"]],
                    "score": p, "up": up, "down": down})
    return sorted(out, key=lambda x: -x["score"])[:limit]


CURRENT_INTERNET = {"mobile": "Mobile hotspot", "home": "Home broadband", "business": "Business broadband",
                    "leased": "Leased line", "none": "None"}   # chat answer -> the leads file's current_internet


def score_application(profile, items: dict | None = None) -> dict:
    """Score a live application from what the chat has learned (the rest counts as average)."""
    seg = {k: v for k, v in SEGMENTS.items()}.get(profile.segment)
    f = {"lead_source": None, "segment": seg, "city_tier": str(profile.city_tier) if profile.city_tier else None,
         "current_internet": CURRENT_INTERNET.get(profile.current_tools), "current_provider": None, "annual_turnover_band": None,
         "has_gstin": {"active": "Y", "inactive": "Y", "none": "N"}.get(profile.gstin_status),
         "has_udyam": None, "employees": profile.employees, "sites": profile.sites, "spend": None,
         "interests": sum(1 for k in profile.needs_answered if getattr(profile.needs, k) is True) or None}
    p, up, down = model().score(f)
    return {"score": p, "up": up, "down": down}

"""Order tracker: one line per product, so the owner can check progress instead of calling support.

Each product is installed in parallel once the documents pass: its "ready by" date is the booking date plus the
product's typical_install_days from the catalogue (SIMs and cloud 1 day, AirFiber 2, fibre 5, leased lines 21-30).
A technician or partner marks a product live in the back office; when every product is live the order is active,
billing starts, and the details read from the documents are deleted (only the KYC result is kept).
"""
from __future__ import annotations

from datetime import date, timedelta

from .catalogue import load_catalogue


def _day(at: str | None) -> date | None:
    return date.fromisoformat(at[:10]) if at else None


def booked_on(a) -> date | None:
    return _day(next((s["at"] for s in reversed(a.timeline) if s["step"] == "installation_booked"), None))


def products(a, items: dict[str, int]) -> list[dict]:
    """status: waiting (documents not passed yet) | installing | live."""
    cat, booked = load_catalogue(), booked_on(a)
    out = []
    for pid, qty in items.items():
        p = cat[pid]
        ready = booked + timedelta(days=p.install_days) if booked else None
        live = a.installed.get(pid)
        out.append({"product_id": pid, "name": p.name, "quantity": qty, "install_days": p.install_days,
                    "status": "live" if live else "installing" if booked else "waiting",
                    "ready_by": ready.isoformat() if ready else None, "live_on": live})
    return sorted(out, key=lambda x: (x["status"] != "live", x["install_days"], x["name"]))


def is_active(a, items: dict[str, int]) -> bool:
    return bool(items) and all(pid in a.installed for pid in items)

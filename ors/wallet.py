"""Team wallet: a hand-edited ledger (wallet.json) summarised for the site.

Every entry is money in (positive amount) or out (negative). The balance is the sum, so
the ledger is the only thing to keep up to date. Dues are worked out from the same
ledger: a player's payments with `who` set, dated on or after `dues.since`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

CENT = Decimal("0.01")


@dataclass
class Entry:
    date: date
    note: str
    amount: Decimal
    who: str = ""

    def to_json(self) -> dict:
        out = {"date": self.date.isoformat(), "note": self.note, "amount": str(self.amount)}
        if self.who:
            out["who"] = self.who
        return out


def _money(raw, where: str) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise ValueError(f"wallet.json {where}: amount must be a number, got {raw!r}")
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        raise ValueError(f"wallet.json {where}: amount must be a number, got {raw!r}") from None
    if not value.is_finite() or value != value.quantize(CENT):
        raise ValueError(f"wallet.json {where}: amount must be dollars and cents, got {raw!r}")
    return value.quantize(CENT)


def _date(raw, where: str) -> date:
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise ValueError(f"wallet.json {where}: date must be YYYY-MM-DD, got {raw!r}") from None


def parse_entries(rows: list) -> list[Entry]:
    entries = []
    for i, r in enumerate(rows or []):
        where = f"entries[{i}]"
        if not isinstance(r, dict):
            raise ValueError(f"wallet.json {where}: expected an object")
        note = str(r.get("note", "")).strip()
        if not note:
            raise ValueError(f"wallet.json {where}: note is required")
        entries.append(Entry(_date(r.get("date"), where), note, _money(r.get("amount"), where), str(r.get("who", "")).strip()))
    entries.sort(key=lambda e: e.date)
    return entries


def summarise(raw: dict | None, *, recent: int = 8) -> dict | None:
    """Balance, totals, recent entries and dues status; None when there's no wallet."""
    if not raw:
        return None
    entries = parse_entries(raw.get("entries", []))
    money_in = sum((e.amount for e in entries if e.amount > 0), Decimal("0.00"))
    money_out = sum((-e.amount for e in entries if e.amount < 0), Decimal("0.00"))

    dues = None
    d = raw.get("dues") or {}
    amount = _money(d.get("amount", 0), "dues")
    if d.get("players") and amount > 0:
        since = _date(d["since"], "dues") if d.get("since") else date.min
        rows = []
        for name in d["players"]:
            key = str(name).strip().casefold()
            paid = sum(
                (e.amount for e in entries if e.amount > 0 and e.who.casefold() == key and e.date >= since),
                Decimal("0.00"),
            )
            status = "paid" if paid >= amount else "partial" if paid > 0 else "owing"
            rows.append({"name": str(name).strip(), "paid": paid, "owes": max(amount - paid, Decimal("0.00")), "status": status})
        dues = {
            "label": str(d.get("label", "Dues")),
            "amount": amount,
            "players": rows,
            "paid_count": sum(r["status"] == "paid" for r in rows),
            "outstanding": sum((r["owes"] for r in rows), Decimal("0.00")),
        }

    return {
        "currency": str(raw.get("currency", "CAD")),
        "how_to_pay": str(raw.get("how_to_pay", "")).strip(),
        "balance": money_in - money_out,
        "money_in": money_in,
        "money_out": money_out,
        "recent": list(reversed(entries))[:recent],
        "count": len(entries),
        "dues": dues,
    }


def to_json(w: dict | None) -> dict | None:
    """JSON-safe copy for data.json (amounts as strings, so no float rounding)."""
    if w is None:
        return None
    dues = w["dues"]
    return {
        **{k: str(w[k]) for k in ("balance", "money_in", "money_out")},
        "currency": w["currency"],
        "how_to_pay": w["how_to_pay"],
        "recent": [e.to_json() for e in w["recent"]],
        "dues": dues and {
            **dues,
            "amount": str(dues["amount"]),
            "outstanding": str(dues["outstanding"]),
            "players": [{**p, "paid": str(p["paid"]), "owes": str(p["owes"])} for p in dues["players"]],
        },
    }


def fmt(amount: Decimal, *, sign: bool = False) -> str:
    """Decimal('-1234.5') -> '−$1,234.50'; sign=True also prefixes '+' on money in."""
    s = f"${abs(amount):,.2f}"
    if amount < 0:
        return "−" + s
    return ("+" + s) if sign and amount > 0 else s

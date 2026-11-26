from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from ors.render import _wallet_card
from ors.wallet import fmt, summarise, to_json

WALLET = {
    "currency": "CAD",
    "how_to_pay": "e-Transfer the captain",
    "dues": {"label": "Winter dues", "amount": 100, "since": "2026-11-01", "players": ["Angus", "Bea", "Cam"]},
    "entries": [
        {"date": "2026-10-20", "note": "Fall dues", "amount": 100, "who": "Bea"},  # before `since`
        {"date": "2026-11-02", "note": "Winter dues", "amount": 100, "who": "angus"},
        {"date": "2026-11-03", "note": "Winter dues", "amount": "40.50", "who": "Bea"},
        {"date": "2026-11-05", "note": "League fee", "amount": -1200},
        {"date": "2026-11-04", "note": "Ref tip", "amount": -0.1},
    ],
}


def test_balance_and_totals_are_exact():
    w = summarise(WALLET)
    assert w["money_in"] == Decimal("240.50")
    assert w["money_out"] == Decimal("1200.10")
    assert w["balance"] == Decimal("-959.60")
    assert [e.note for e in w["recent"]][:2] == ["League fee", "Ref tip"]  # newest first


def test_dues_from_ledger():
    d = summarise(WALLET)["dues"]
    by = {p["name"]: (p["status"], p["owes"]) for p in d["players"]}
    assert by == {"Angus": ("paid", 0), "Bea": ("partial", Decimal("59.50")), "Cam": ("owing", 100)}
    assert d["paid_count"] == 1 and d["outstanding"] == Decimal("159.50")


def test_dues_hidden_without_amount_or_players():
    assert summarise({**WALLET, "dues": {"amount": 0, "players": ["A"]}})["dues"] is None
    assert summarise({**WALLET, "dues": {"amount": 50, "players": []}})["dues"] is None
    assert summarise(None) is None


@pytest.mark.parametrize(
    "entry",
    [
        {"date": "2026-11-01", "note": "x", "amount": "lots"},
        {"date": "2026-11-01", "note": "x", "amount": 1.005},
        {"date": "2026-11-01", "note": "x", "amount": True},
        {"date": "Nov 1", "note": "x", "amount": 1},
        {"date": "2026-11-01", "note": "", "amount": 1},
    ],
)
def test_bad_entries_fail_loudly(entry):
    with pytest.raises(ValueError, match="wallet.json entries"):
        summarise({"entries": [entry]})


def test_fmt():
    assert fmt(Decimal("-1234.5")) == "−$1,234.50"
    assert fmt(Decimal("5"), sign=True) == "+$5.00"
    assert fmt(Decimal("0"), sign=True) == "$0.00"


def test_json_and_card():
    w = summarise(WALLET)
    j = to_json(w)
    assert j["balance"] == "-959.60" and j["dues"]["players"][1]["owes"] == "59.50"
    html = _wallet_card(w)
    assert "−$959.60" in html and "1 of 3 paid" in html and "e-Transfer the captain" in html
    assert _wallet_card(summarise({"entries": []})).count("No transactions yet") == 1
    assert "<script>" not in _wallet_card(summarise({"entries": [{"date": "2026-11-01", "note": "<script>", "amount": 1}]}))

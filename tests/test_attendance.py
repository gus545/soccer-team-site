import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import attendance  # noqa: E402


@pytest.fixture
def api(monkeypatch):
    store: dict[tuple, dict] = {}
    monkeypatch.setattr(attendance, "known_games", lambda: {"4307170"})
    monkeypatch.setattr(attendance, "db_query", lambda g: [dict(v) for (gg, _), v in store.items() if gg == g])
    monkeypatch.setattr(attendance, "db_put", lambda item: store.__setitem__((item["game"], item["player"]), item))
    monkeypatch.setattr(attendance, "db_delete", lambda key: store.pop((key["game"], key["player"]), None))
    return store


def call(method, *, game=None, body=None):
    ev = {"requestContext": {"http": {"method": method}}}
    if game is not None:
        ev["queryStringParameters"] = {"game": game}
    if body is not None:
        ev["body"] = json.dumps(body)
    r = attendance.handler(ev)
    return r["statusCode"], json.loads(r["body"])


def test_rsvp_flow(api):
    assert call("GET", game="4307170") == (200, {"game": "4307170", "players": []})
    code, out = call("POST", body={"game": "4307170", "name": "  Angus  ", "status": "in"})
    assert code == 200 and [(p["name"], p["status"]) for p in out["players"]] == [("Angus", "in")]
    # Same person, different case: updates rather than duplicating.
    code, out = call("POST", body={"game": "4307170", "name": "angus", "status": "out"})
    assert [(p["name"], p["status"]) for p in out["players"]] == [("angus", "out")]
    # Empty status removes you.
    code, out = call("POST", body={"game": "4307170", "name": "Angus", "status": ""})
    assert out["players"] == []


def test_rejects_unknown_game_and_bad_input(api):
    assert call("GET", game="999")[0] == 404
    assert call("GET", game="abc")[0] == 404
    assert call("POST", body={"game": "4307170", "name": "", "status": "in"})[0] == 400
    assert call("POST", body={"game": "4307170", "name": "x" * 31, "status": "in"})[0] == 400
    assert call("POST", body={"game": "4307170", "name": "<script>", "status": "in"})[0] == 400
    assert call("POST", body={"game": "4307170", "name": "Zoë O'Neil-Smith", "status": "in"})[0] == 200
    assert call("POST", body={"game": "4307170", "name": "A", "status": "yes"})[0] == 400
    assert call("DELETE")[0] == 405


def test_game_cap(api, monkeypatch):
    monkeypatch.setattr(attendance, "MAX_PLAYERS", 2)
    for n in ("A", "B"):
        assert call("POST", body={"game": "4307170", "name": n, "status": "in"})[0] == 200
    assert call("POST", body={"game": "4307170", "name": "C", "status": "in"})[0] == 429
    # Existing players can still change their answer when full.
    assert call("POST", body={"game": "4307170", "name": "a", "status": "maybe"})[0] == 200

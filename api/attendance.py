"""Attendance API: Lambda behind CloudFront at /api/attendance.

GET  /api/attendance?game=<event_id>             -> {"game": "...", "players": [...]}
POST /api/attendance {"game", "name", "status"}  -> same shape, after saving
     status is "in" | "out" | "maybe", or "" to remove yourself.

Deliberately no login, so it's as easy as an Instagram poll. Guard rails: only games
listed in the site's data.json are accepted, names are short and plain, and each game
holds a limited number of entries.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.request

STATUSES = {"in", "out", "maybe"}
MAX_NAME = 30
MAX_PLAYERS = 40
TTL_SECONDS = 120 * 24 * 3600
GAMES_CACHE_SECONDS = 300

_table = None
_games: tuple[float, set[str]] = (0.0, set())


def table():
    global _table
    if _table is None:
        import boto3

        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


def known_games() -> set[str]:
    """Event ids present on the published site (cached for a few minutes)."""
    global _games
    fetched, ids = _games
    if time.time() - fetched < GAMES_CACHE_SECONDS and ids:
        return ids
    req = urllib.request.Request(os.environ["SITE_DATA_URL"], headers={"User-Agent": "ors-attendance"})
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.load(r)
    ids = {str(g["event_id"]) for s in data.get("seasons", []) for g in s.get("games", []) if g.get("event_id")}
    _games = (time.time(), ids)
    return ids


def clean_name(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    name = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw)).strip()
    if not 1 <= len(name) <= MAX_NAME:
        return None
    if not all(ch.isalnum() or ch in " .'-" for ch in name):
        return None
    return name


def player_key(name: str) -> str:
    return name.casefold()


# -- storage (swapped for a fake in tests) --------------------------------------------
def db_query(game: str) -> list[dict]:
    from boto3.dynamodb.conditions import Key

    return table().query(KeyConditionExpression=Key("game").eq(game)).get("Items", [])


def db_put(item: dict) -> None:
    table().put_item(Item=item)


def db_delete(key: dict) -> None:
    table().delete_item(Key=key)


def players(game: str) -> list[dict]:
    items = db_query(game)
    items.sort(key=lambda i: int(i.get("updated", 0)))
    return [{"name": i["name"], "status": i["status"], "updated": int(i.get("updated", 0))} for i in items]


def resp(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body),
    }


def handler(event, context=None):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    try:
        if method == "GET":
            game = (event.get("queryStringParameters") or {}).get("game", "")
            return _get(game)
        if method == "POST":
            body = event.get("body") or "{}"
            if event.get("isBase64Encoded"):
                import base64

                body = base64.b64decode(body).decode()
            if len(body) > 1000:
                return resp(413, {"error": "Too large"})
            return _post(json.loads(body))
        return resp(405, {"error": "Method not allowed"})
    except json.JSONDecodeError:
        return resp(400, {"error": "Bad JSON"})


def _valid_game(game) -> str | None:
    game = str(game or "")
    if not re.fullmatch(r"\d{1,12}", game):
        return None
    return game if game in known_games() else None


def _get(game) -> dict:
    game = _valid_game(game)
    if not game:
        return resp(404, {"error": "Unknown game"})
    return resp(200, {"game": game, "players": players(game)})


def _post(data: dict) -> dict:
    if not isinstance(data, dict):
        return resp(400, {"error": "Bad request"})
    game = _valid_game(data.get("game"))
    if not game:
        return resp(404, {"error": "Unknown game"})
    name = clean_name(data.get("name"))
    if not name:
        return resp(400, {"error": f"Name must be 1-{MAX_NAME} letters, numbers, spaces or .'-"})
    status = data.get("status", "")
    key = {"game": game, "player": player_key(name)}

    if status == "":
        db_delete(key)
        return resp(200, {"game": game, "players": players(game)})
    if status not in STATUSES:
        return resp(400, {"error": "Status must be in, out or maybe"})

    current = players(game)
    if len(current) >= MAX_PLAYERS and all(player_key(p["name"]) != key["player"] for p in current):
        return resp(429, {"error": "This game is full"})

    now = int(time.time())
    db_put({**key, "name": name, "status": status, "updated": now, "expires": now + TTL_SECONDS})
    return resp(200, {"game": game, "players": players(game)})

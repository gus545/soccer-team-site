"""Turn raw TeamLinkt rows into plain game/standing records."""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

_TAGS = re.compile(r"<[^>]+>")
_SCORE = re.compile(r"^(.*?)\s*\((\d+)\)\s*$")
_EVENT_ID = re.compile(r"/event/\d+/(\d+)")
_TEAM_ID = re.compile(r"/team/\d+/(\d+)")
_MAPS = re.compile(r'href="(https?://maps\.google\.com[^"]+)"')


def text(fragment: str) -> str:
    return html.unescape(_TAGS.sub("", fragment or "")).strip()


def norm(name: str) -> str:
    """Case/whitespace-insensitive key for matching team names across seasons."""
    return re.sub(r"\s+", " ", name).strip().casefold()


def split_score(label: str) -> tuple[str, int | None]:
    """'The 7 Deadly Shins (12)' -> ('The 7 Deadly Shins', 12). Unscored -> (name, None)."""
    m = _SCORE.match(label)
    return (m.group(1).strip(), int(m.group(2))) if m else (label.strip(), None)


@dataclass
class Game:
    event_id: int | None
    kind: str  # "Game", "Exhibition Game", ...
    start: datetime
    end: datetime
    home: str
    away: str
    home_id: int | None
    away_id: int | None
    home_score: int | None
    away_score: int | None
    location: str
    map_url: str | None
    summary_url: str | None
    # Filled in relative to our team:
    side: str = ""  # "HOME" | "AWAY"
    opponent: str = ""
    result: str | None = None  # "W" | "L" | "T" | None
    kit: dict = field(default_factory=dict)

    @property
    def played(self) -> bool:
        return self.home_score is not None and self.away_score is not None

    @property
    def exhibition(self) -> bool:
        return "exhibition" in self.kind.lower()

    def to_json(self) -> dict:
        d = asdict(self)
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat()
        d["played"] = self.played
        d["exhibition"] = self.exhibition
        return d


def parse_time_range(date_s: str, time_s: str, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """('Sun Nov 29, 2026', '4:00 PM - 4:55 PM') -> aware start/end datetimes.

    TeamLinkt's numeric timestamp column is offset by an hour from the displayed time,
    so we trust the human-readable strings and localise them ourselves.
    """
    day = datetime.strptime(date_s.strip(), "%a %b %d, %Y").date()
    parts = [p.strip() for p in time_s.split("-")]
    start_t = datetime.strptime(parts[0], "%I:%M %p").time()
    end_t = datetime.strptime(parts[1], "%I:%M %p").time() if len(parts) > 1 else start_t
    start = datetime.combine(day, start_t, tz)
    end = datetime.combine(day, end_t, tz)
    return start, end


def parse_event(row: dict, tz: ZoneInfo) -> Game:
    start, end = parse_time_range(row["0"], row["1"], tz)
    title_html = row.get("2", "")
    home, home_score = split_score(text(row.get("3", "")))
    away, away_score = split_score(text(row.get("4", "")))
    ev = _EVENT_ID.search(title_html)
    maps = _MAPS.search(row.get("5", ""))
    summary = re.search(r'href="([^"]+)"', title_html)
    home_id = row.get("home_association_team_id") or _first_int(_TEAM_ID, row.get("3", ""))
    # (sic) TeamLinkt spells this key "assocation"
    away_id = (
        row.get("away_assocation_team_id")
        or row.get("away_association_team_id")
        or _first_int(_TEAM_ID, row.get("4", ""))
    )
    return Game(
        event_id=int(ev.group(1)) if ev else None,
        kind=text(title_html).replace("[Summary]", "").strip() or "Game",
        start=start,
        end=end,
        home=home,
        away=away,
        home_id=int(home_id) if home_id else None,
        away_id=int(away_id) if away_id else None,
        home_score=home_score,
        away_score=away_score,
        location=text(row.get("5", "")),
        map_url=html.unescape(maps.group(1)) if maps else None,
        summary_url=html.unescape(summary.group(1)) if summary else None,
    )


def _first_int(rx: re.Pattern, s: str) -> int | None:
    m = rx.search(s or "")
    return int(m.group(1)) if m else None


def orient(game: Game, team_id: int | None, team_name: str) -> Game:
    """Fill side/opponent/result from our team's point of view."""
    is_home = (team_id and game.home_id == team_id) or norm(game.home) == norm(team_name)
    game.side = "HOME" if is_home else "AWAY"
    game.opponent = game.away if is_home else game.home
    if game.played:
        us, them = (
            (game.home_score, game.away_score) if is_home else (game.away_score, game.home_score)
        )
        game.result = "W" if us > them else "L" if us < them else "T"
    return game


# -- Shirt colours ---------------------------------------------------------------------
def _colours_for(colours: dict, name: str) -> dict | None:
    key = norm(name)
    for k, v in colours.items():
        if not k.startswith("_") and norm(k) == key:
            return v
    return None


def _known(c: str | None) -> bool:
    return bool(c) and c.strip().upper() not in {"TBD", "?", "UNKNOWN"}


def pick_kit(side: str, us: dict | None, them: dict | None) -> dict:
    """Same rule as the Discord bot: home wears primary; away changes on a clash.

    Returns {"wear": str, "reason": str}.
    """
    if not us or not _known(us.get("primary")):
        return {"wear": "?", "reason": "Set our colours in colours.json"}
    primary, secondary = us["primary"], us.get("secondary")
    alt = us.get("alt") or "pinnies"
    if side == "HOME":
        return {"wear": primary, "reason": "Home team wears primary"}
    if not them or not _known(them.get("primary")):
        return {"wear": primary, "reason": "Opponent colours unknown; confirm before the game"}
    theirs = {c.strip().casefold() for c in (them.get("primary"), them.get("secondary")) if _known(c)}
    if primary.casefold() not in theirs:
        return {"wear": primary, "reason": f"No clash with {them['primary']}"}
    if _known(secondary) and secondary.casefold() not in theirs:
        return {"wear": secondary, "reason": f"Clash with home {them['primary']}; away changes"}
    return {"wear": alt, "reason": "Both our colours clash"}


def apply_kits(games: list[Game], team_name: str, colours: dict) -> None:
    us = _colours_for(colours, team_name)
    for g in games:
        g.kit = pick_kit(g.side, us, _colours_for(colours, g.opponent))


# -- Standings -------------------------------------------------------------------------
STANDING_FIELDS = (
    "ranking",
    "games_played",
    "total_wins",
    "total_losses",
    "total_ties",
    "total_points",
    "score_for",
    "score_against",
    "score_differential",
    "streak_type",
    "streak_length",
)


def parse_standings(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        team = r.get("Team") or {}
        rec = {k: r.get(k) for k in STANDING_FIELDS}
        rec["team_id"] = r.get("team_id") or team.get("id")
        rec["team"] = team.get("name") or text(r.get("team_name", ""))
        out.append(rec)
    out.sort(
        key=lambda s: (
            -(s["total_points"] or 0),
            -(s["score_differential"] or 0),
            -(s["score_for"] or 0),
            s["team"].casefold(),
        )
    )
    for i, s in enumerate(out, 1):
        s["position"] = i
    return out

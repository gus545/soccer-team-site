from datetime import datetime
from zoneinfo import ZoneInfo

from ors.build import season_label
from ors.ics import build_calendar
from ors.model import (
    orient,
    parse_event,
    parse_standings,
    pick_kit,
    split_score,
)

TZ = ZoneInfo("America/Toronto")
US = 947085

# Real rows captured from /leagues/getAllEvents/26108 (Fall 2026).
PLAYED = {
    "0": "Sun Nov 15, 2026",
    "1": "2:00 PM - 2:55 PM",
    "2": 'Game <a href="https://leagues.teamlinkt.com/Leagues/event/26108/4301234" target="_blank">[Summary]</a>',
    "3": '<a href="/leagues/team/26108/955138" style=""><span class="tooltips">Co-ed Mixed Indy 1 (1)</span></a>',
    "4": '<a href="/leagues/team/26108/947085" style=""><span class="tooltips">The 7 Deadly Shins (12)</span></a>',
    "5": '<a target="_blank" href="https://maps.google.com/maps?q=45.47,-75.49">Orleans Dome Field #3</a>',
    "6": 1794772800,
    "home_association_team_id": 955138,
    "away_assocation_team_id": 947085,
}
UPCOMING = {
    "0": "Sun Nov 29, 2026",
    "1": "1:30 PM - 2:25 PM",
    "2": 'Exhibition Game <a href="https://leagues.teamlinkt.com/Leagues/event/26108/4307170">[Summary]</a>',
    "3": '<a href="/leagues/team/26108/947085"><span>The 7 Deadly Shins</span></a>',
    "4": '<a href="/leagues/team/26108/957739"><span>Sons of Pitches</span></a>',
    "5": "Louis Riel Dome Turf Field #1",
    "home_association_team_id": 947085,
    "away_assocation_team_id": 957739,
}


def test_split_score():
    assert split_score("The 7 Deadly Shins (12)") == ("The 7 Deadly Shins", 12)
    assert split_score("Sons of Pitches") == ("Sons of Pitches", None)
    # Parenthesised non-numeric suffixes are part of the name, not a score.
    assert split_score("Honeybadgers (winter 2026)") == ("Honeybadgers (winter 2026)", None)
    assert split_score("Honeybadgers (winter 2026) (3)") == ("Honeybadgers (winter 2026)", 3)


def test_parse_played_away_win():
    g = orient(parse_event(PLAYED, TZ), US, "The 7 Deadly Shins")
    assert g.event_id == 4301234
    assert g.start == datetime(2026, 11, 15, 14, 0, tzinfo=TZ)
    assert g.end.hour == 14 and g.end.minute == 55
    assert (g.home, g.away, g.home_score, g.away_score) == ("Co-ed Mixed Indy 1", "The 7 Deadly Shins", 1, 12)
    assert g.side == "AWAY" and g.opponent == "Co-ed Mixed Indy 1" and g.result == "W"
    assert g.map_url.startswith("https://maps.google.com") and g.location == "Orleans Dome Field #3"
    assert not g.exhibition


def test_parse_upcoming_home():
    g = orient(parse_event(UPCOMING, TZ), US, "The 7 Deadly Shins")
    assert g.side == "HOME" and g.opponent == "Sons of Pitches"
    assert not g.played and g.result is None
    assert g.exhibition and g.map_url is None
    # Toronto is UTC-5 in November.
    assert g.start.utcoffset().total_seconds() == -5 * 3600


def test_orient_falls_back_to_name_when_ids_missing():
    row = {**PLAYED, "home_association_team_id": None, "away_assocation_team_id": None}
    row["3"] = row["3"].replace("/team/26108/955138", "")
    row["4"] = row["4"].replace("/team/26108/947085", "")
    g = orient(parse_event(row, TZ), 999, "the 7 deadly shins")
    assert g.side == "AWAY" and g.result == "W"


def test_kit_rules():
    us = {"primary": "Black", "secondary": "White", "alt": "pinnies"}
    assert pick_kit("HOME", us, {"primary": "Black"})["wear"] == "Black"
    assert pick_kit("AWAY", us, {"primary": "Red", "secondary": "Blue"})["wear"] == "Black"
    assert pick_kit("AWAY", us, {"primary": "black"})["wear"] == "White"
    assert pick_kit("AWAY", us, {"primary": "Black", "secondary": "White"})["wear"] == "pinnies"
    assert pick_kit("AWAY", us, None)["wear"] == "Black"
    assert pick_kit("AWAY", {"primary": "TBD"}, None)["wear"] == "?"


def test_standings_sorted_by_points_then_gd():
    rows = [
        {"team_id": 1, "Team": {"name": "A"}, "total_points": 6, "score_differential": 1, "score_for": 9},
        {"team_id": 2, "Team": {"name": "B"}, "total_points": 9, "score_differential": -2, "score_for": 5},
        {"team_id": 3, "Team": {"name": "C"}, "total_points": 6, "score_differential": 4, "score_for": 8},
    ]
    assert [(s["team"], s["position"]) for s in parse_standings(rows)] == [("B", 1), ("C", 2), ("A", 3)]


def test_season_label():
    assert season_label("Sun-Soccer-Wint-26-27") == "Sunday Winter 2026-27"
    assert season_label("Sun-Soccer-Fall-2026") == "Sunday Fall 2026"


def test_calendar_is_valid_shape():
    games = [orient(parse_event(r, TZ), US, "The 7 Deadly Shins") for r in (PLAYED, UPCOMING)]
    for g in games:
        g.kit = {"wear": "Black", "reason": "Home team wears primary"}
    ics = build_calendar("The 7 Deadly Shins", games, site_url="https://x.test", now=datetime(2026, 11, 25, tzinfo=TZ))
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == 2
    assert "UID:teamlinkt-4301234@macgillivary.dev" in ics
    assert "DTSTART:20261115T190000Z" in ics  # 2 PM EST
    assert "W 12-1" in ics
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))

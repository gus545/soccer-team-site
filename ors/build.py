"""Scrape TeamLinkt and write the static site into an output directory.

    python -m ors.build dist
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .ics import build_calendar
from .model import apply_kits, norm, orient, parse_event, parse_standings
from .render import render_page
from .teamlinkt import TeamLinkt
from .wallet import summarise, to_json as wallet_json

ROOT = Path(__file__).resolve().parent.parent


def season_label(name: str) -> str:
    """'Sun-Soccer-Wint-26-27' -> 'Sunday Winter 2026-27'."""
    words = {"Sun": "Sunday", "Wint": "Winter", "Fall": "Fall", "Spr": "Spring", "Summ": "Summer"}
    parts = [p for p in name.split("-") if p.lower() != "soccer"]
    out, years = [], []
    for p in parts:
        if re.fullmatch(r"\d{2}|\d{4}", p):
            years.append(p if len(p) == 4 else f"20{p}")
        else:
            out.append(words.get(p, p))
    if len(years) == 2:
        out.append(f"{years[0]}-{years[1][-2:]}")
    elif years:
        out.append(years[0])
    return " ".join(out)


def find_team_seasons(tl: TeamLinkt, cfg: dict) -> list[dict]:
    """Newest-first seasons (matching the prefix) that our team is registered in."""
    seasons = [s for s in tl.seasons() if str(s["name"]).startswith(cfg["season_prefix"])]
    seasons.sort(key=lambda s: s["id"], reverse=True)  # ids increase over time
    want = norm(cfg["team_name"])
    found = []
    for s in seasons:
        rows = tl.standings(s["id"])
        match = next((r for r in parse_standings(rows) if norm(r["team"]) == want), None)
        if match:
            found.append({**s, "team_id": match["team_id"]})
            if len(found) >= cfg.get("seasons_to_show", 1):
                break
    return found


def scrape_season(tl: TeamLinkt, cfg: dict, season: dict, colours: dict, tz: ZoneInfo) -> dict:
    sid, team_id = season["id"], season["team_id"]
    division, table = None, []
    for d in tl.divisions(sid):
        rows = parse_standings(tl.standings(sid, d["id"]))
        if any(r["team_id"] == team_id for r in rows):
            division, table = d["name"], rows
            break
    if not table:  # not placed in a division yet; fall back to the whole season table
        table = parse_standings(tl.standings(sid))

    games = [orient(parse_event(r, tz), team_id, cfg["team_name"]) for r in tl.team_events(sid, team_id)]
    games.sort(key=lambda g: g.start)
    apply_kits(games, cfg["team_name"], colours)

    record = next((r for r in table if r["team_id"] == team_id), None)
    return {
        "id": sid,
        "name": season["name"],
        "label": season_label(season["name"]),
        "team_id": team_id,
        "division": division,
        "record": record,
        "standings": table,
        "games": games,
    }


def load_wallet() -> dict | None:
    path = ROOT / "wallet.json"
    return json.loads(path.read_text()) if path.exists() else None


def build(
    out_dir: Path, *, cfg: dict | None = None, colours: dict | None = None, wallet: dict | None = None, now=None
) -> dict:
    cfg = cfg or json.loads((ROOT / "config.json").read_text())
    colours = colours if colours is not None else json.loads((ROOT / "colours.json").read_text())
    # Validate the hand-edited ledger before scraping, so a typo fails the build fast.
    wallet = summarise(wallet if wallet is not None else load_wallet())
    tz = ZoneInfo(cfg["timezone"])
    now = now or datetime.now(tz)
    tl = TeamLinkt(cfg["association_id"], cfg["league_slug"])

    seasons = [scrape_season(tl, cfg, s, colours, tz) for s in find_team_seasons(tl, cfg)]
    if not seasons:
        raise SystemExit(f"No {cfg['season_prefix']} season found containing {cfg['team_name']!r}")

    all_games = [g for s in seasons for g in s["games"]]
    upcoming = sorted((g for g in all_games if g.end >= now), key=lambda g: g.start)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / cfg["calendar_file"]).write_text(
        build_calendar(cfg["team_name"], sorted(all_games, key=lambda g: g.start), site_url=cfg["site_url"], now=now),
        encoding="utf-8",
        newline="",
    )
    data = {
        "generated_at": now.isoformat(timespec="seconds"),
        "team": cfg["team_name"],
        "next_game": upcoming[0].to_json() if upcoming else None,
        "seasons": [{**s, "games": [g.to_json() for g in s["games"]]} for s in seasons],
        "wallet": wallet_json(wallet),
    }
    (out_dir / "data.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "index.html").write_text(
        render_page(cfg, seasons, upcoming[0] if upcoming else None, now, wallet), encoding="utf-8"
    )
    static = ROOT / "static"
    if static.is_dir():
        shutil.copytree(static, out_dir, dirs_exist_ok=True)
    return data


def main(argv: list[str]) -> None:
    out = Path(argv[1] if len(argv) > 1 else "dist")
    data = build(out)
    s = data["seasons"][0]
    print(
        f"Built {out}/: {data['team']} - {s['label']} ({s['division'] or 'no division'}), "
        f"{len(s['games'])} games; next: {data['next_game']['start'] if data['next_game'] else 'none'}"
    )


if __name__ == "__main__":
    main(sys.argv)

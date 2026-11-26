"""Thin client for the public TeamLinkt league-site endpoints used by ottawarecsports.

These are the same unauthenticated AJAX endpoints the league website calls from the
browser. Quirks worth knowing:

* ``getAllEvents`` ignores ``start=0`` and jumps to "today" unless ``prev_team_id``
  equals ``team_id`` (it treats a changed filter as a fresh page load). We always send
  them equal and ask for everything in one page.
* ``status`` is ignored; past and future games come back together.
* The division filter on ``getAllEvents`` is unreliable, so we filter by team instead.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request

BASE = "https://leagues.teamlinkt.com"
UA = "ors-soccer-scraper/1.0 (+https://soccer.macgillivary.dev)"


class TeamLinkt:
    def __init__(self, association_id: int, league_slug: str, *, retries: int = 3):
        self.aid = association_id
        self.slug = league_slug
        self.retries = retries

    # -- HTTP -------------------------------------------------------------------------
    def _request(self, path: str, data: dict | None = None) -> str:
        body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
        req = urllib.request.Request(
            BASE + path,
            data=body,
            headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"},
            method="POST" if body is not None else "GET",
        )
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return resp.read().decode("utf-8")
            except Exception as e:  # noqa: BLE001 - retry any network error
                last = e
                time.sleep(2**attempt)
        raise RuntimeError(f"TeamLinkt request failed: {path}") from last

    def _json(self, path: str, data: dict) -> dict:
        text = self._request(path, data)
        out = json.loads(text)
        if isinstance(out, str):  # some endpoints double-encode
            out = json.loads(out)
        return out

    # -- Seasons & divisions ----------------------------------------------------------
    def seasons(self) -> list[dict]:
        """All seasons in the league-site dropdown: [{id, name}]."""
        page = self._request(f"/{self.slug}/Schedule")
        return _select_options(page, "season_id")

    def divisions(self, season_id: int) -> list[dict]:
        """Divisions for a season: [{id, name}] (excludes the 'All Divisions' option)."""
        page = self._request(
            f"/{self.slug}/Schedule",
            {
                "_method": "POST",
                "data[schedule_type]": "regular_season",
                "data[season_id]": season_id,
            },
        )
        return [d for d in _select_options(page, "hierarchy_filter") if d["id"]]

    # -- Data -------------------------------------------------------------------------
    def standings(self, season_id: int, division_id: int | str = "") -> list[dict]:
        data = self._json(
            f"/leagues/getStandings/{self.aid}/{season_id}",
            {"season_id": season_id, "group_ids[division]": division_id},
        )
        return data.get("standings") or []

    def team_events(self, season_id: int, team_id: int) -> list[dict]:
        rows: list[dict] = []
        start, page = 0, 200
        while True:
            data = self._json(
                f"/leagues/getAllEvents/{self.aid}",
                {
                    "draw": 1,
                    "filters[division]": "",
                    "status": "past",
                    "length": page,
                    "start": start,
                    "team_id": team_id,
                    "prev_team_id": team_id,
                    "prev_filter_id": "",
                    "type": "schedule",
                    "is_league_site": 1,
                    "show_team_links": 1,
                    "season_id": season_id,
                    "show_games_only": 1,
                    "schedule_type": "regular_season",
                    "location_id": "",
                },
            )
            batch = data.get("data") or []
            rows.extend(batch)
            total = int(data.get("recordsTotal") or 0)
            start += len(batch)
            if not batch or start >= total:
                return rows


def _select_options(page: str, select_id: str) -> list[dict]:
    m = re.search(rf'<select[^>]*id="{select_id}"[^>]*>(.*?)</select>', page, re.S)
    if not m:
        return []
    return [
        {"id": int(v) if v.isdigit() else v, "name": html.unescape(n).strip()}
        for v, n in re.findall(r'<option value="([^"]*)"[^>]*>(.*?)</option>', m.group(1), re.S)
    ]

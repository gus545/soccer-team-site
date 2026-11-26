"""Server-side render of the single team page (no JS framework, no build step)."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape as e
from urllib.parse import quote

from .model import Game


def _day(dt: datetime) -> str:
    return dt.strftime("%a %b ") + str(dt.day)


def _clock(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def _ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _swatch(colour: str) -> str:
    safe = colour if re.fullmatch(r"[#a-zA-Z0-9 ]{1,30}", colour or "") else ""
    return f'<span class="swatch" style="--c:{e(safe)}"></span>' if safe and safe != "?" else ""


def _scoreline(g: Game) -> str:
    if not g.played:
        return ""
    us, them = (g.home_score, g.away_score) if g.side == "HOME" else (g.away_score, g.home_score)
    return f"{us}–{them}"


def _next_card(g: Game | None, now: datetime) -> str:
    if not g:
        return """
<section class="card next empty">
  <p class="eyebrow">Next game</p>
  <h2>Schedule not posted yet</h2>
  <p class="muted">ORS hasn't published games for our division. This page checks TeamLinkt every few hours and will update on its own.</p>
</section>"""
    days = (g.start.date() - now.date()).days
    when = "Today" if days == 0 else "Tomorrow" if days == 1 else f"In {days} days"
    loc = (
        f'<a href="{e(g.map_url)}" target="_blank" rel="noopener">{e(g.location)}</a>'
        if g.map_url
        else e(g.location)
    )
    kit = g.kit or {}
    return f"""
<section class="card next">
  <p class="eyebrow">Next game · {when}</p>
  <h2><span class="side side-{g.side.lower()}">{'vs' if g.side == 'HOME' else '@'}</span> {e(g.opponent)}</h2>
  <dl class="facts">
    <div><dt>When</dt><dd>{_day(g.start)} · {_clock(g.start)}–{_clock(g.end)}</dd></div>
    <div><dt>Where</dt><dd>{loc}</dd></div>
    <div><dt>We're</dt><dd>{'Home' if g.side == 'HOME' else 'Away'}{' · exhibition' if g.exhibition else ''}</dd></div>
    <div><dt>Wear</dt><dd>{_swatch(kit.get('wear', ''))}<strong>{e(kit.get('wear', '?'))}</strong> <span class="muted">— {e(kit.get('reason', ''))}</span></dd></div>
  </dl>
</section>"""


def _games_list(games: list[Game], now: datetime) -> str:
    if not games:
        return '<p class="muted">No games scheduled yet.</p>'
    rows = []
    for g in games:
        past = g.end < now
        if g.result:
            badge = f'<span class="res res-{g.result.lower()}">{g.result}</span><span class="score">{_scoreline(g)}</span>'
        elif past:
            badge = '<span class="res res-na" title="Score not reported">–</span>'
        else:
            badge = f'<span class="kit">{_swatch(g.kit.get("wear", ""))}{e(g.kit.get("wear", ""))}</span>'
        tag = ' <span class="tag">exh</span>' if g.exhibition else ""
        loc = (
            f'<a href="{e(g.map_url)}" target="_blank" rel="noopener">{e(g.location)}</a>'
            if g.map_url
            else e(g.location)
        )
        rows.append(
            f"""<li class="game{' past' if past else ''}">
  <div class="g-when"><span class="g-day">{_day(g.start)}</span><span class="g-time">{_clock(g.start)}</span></div>
  <div class="g-main"><span class="g-opp"><span class="side side-{g.side.lower()}">{'vs' if g.side == 'HOME' else '@'}</span> {e(g.opponent)}{tag}</span><span class="g-loc">{loc}</span></div>
  <div class="g-res">{badge}</div>
</li>"""
        )
    return '<ol class="games">' + "\n".join(rows) + "</ol>"


def _standings_table(rows: list[dict], team_id: int) -> str:
    if not rows:
        return '<p class="muted">No standings yet.</p>'
    body = []
    for r in rows:
        gd = r.get("score_differential") or 0
        body.append(
            f"""<tr{' class="us"' if r['team_id'] == team_id else ''}>
  <td class="num">{r['position']}</td><td class="team">{e(r['team'])}</td>
  <td class="num">{r['games_played'] or 0}</td><td class="num">{r['total_wins'] or 0}</td>
  <td class="num">{r['total_losses'] or 0}</td><td class="num">{r['total_ties'] or 0}</td>
  <td class="num hide-sm">{r['score_for'] or 0}</td><td class="num hide-sm">{r['score_against'] or 0}</td>
  <td class="num">{'+' if gd > 0 else ''}{gd}</td><td class="num pts">{r['total_points'] or 0}</td>
</tr>"""
        )
    return f"""<div class="table-wrap"><table class="standings">
<thead><tr><th class="num">#</th><th>Team</th><th class="num" title="Games played">GP</th><th class="num">W</th><th class="num">L</th><th class="num">T</th><th class="num hide-sm" title="Goals for">GF</th><th class="num hide-sm" title="Goals against">GA</th><th class="num" title="Goal difference">GD</th><th class="num">Pts</th></tr></thead>
<tbody>{''.join(body)}</tbody></table></div>"""


def _record_chips(season: dict) -> str:
    r = season.get("record")
    if not r or not r.get("games_played"):
        return ""
    n = len(season["standings"])
    return f"""<ul class="chips">
  <li><b>{r['total_wins'] or 0}-{r['total_losses'] or 0}-{r['total_ties'] or 0}</b><span>W-L-T</span></li>
  <li><b>{r['total_points'] or 0}</b><span>points</span></li>
  <li><b>{_ordinal(r['position'])}</b><span>of {n}</span></li>
</ul>"""


def _season_block(season: dict, now: datetime, *, current: bool, open_: bool = False) -> str:
    sub = " · ".join(x for x in (season["label"], season["division"]) if x)
    inner = f"""
  <h3>Games</h3>
  {_games_list(season['games'], now)}
  <h3>Standings{f" — {e(season['division'])}" if season['division'] else ''}</h3>
  {_standings_table(season['standings'], season['team_id'])}"""
    if current:
        return f'<section class="season">{inner}</section>'
    return f"""<details class="season prior"{' open' if open_ else ''}><summary>{e(sub)} {_record_chips(season)}</summary>{inner}</details>"""


def render_page(cfg: dict, seasons: list[dict], next_game: Game | None, now: datetime) -> str:
    cur = seasons[0]
    team = cfg["team_name"]
    host = re.sub(r"^https?://", "", cfg["site_url"]).rstrip("/")
    ics_https = f"{cfg['site_url'].rstrip('/')}/{cfg['calendar_file']}"
    ics_webcal = f"webcal://{host}/{cfg['calendar_file']}"
    gcal = "https://calendar.google.com/calendar/render?cid=" + quote(ics_webcal, safe="")
    sub = " · ".join(x for x in (cur["label"], cur["division"]) if x)
    # While the newest season has no schedule yet, keep the previous one expanded.
    prior = "\n".join(
        _season_block(s, now, current=False, open_=(i == 0 and not cur["games"]))
        for i, s in enumerate(seasons[1:])
    )
    updated = now.strftime("%b ") + f"{now.day}, " + _clock(now)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(team)}</title>
<meta name="description" content="Schedule, results and standings for {e(team)} — Ottawa Rec Sports {e(sub)}.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚽</text></svg>">
<link rel="alternate" type="text/calendar" title="{e(team)} games" href="{e(ics_https)}">
<link rel="stylesheet" href="styles.css">
</head>
<body>
<main>
  <header class="hero">
    <p class="eyebrow">Ottawa Rec Sports · Co-Ed Soccer</p>
    <h1>{e(team)}</h1>
    <p class="sub">{e(sub)}</p>
    {_record_chips(cur)}
  </header>

  {_next_card(next_game, now)}

  <section class="card subscribe">
    <div>
      <h2>Add games to your calendar</h2>
      <p class="muted">Subscribe once; new games and scores show up automatically.</p>
    </div>
    <div class="btns">
      <a class="btn primary" href="{e(ics_webcal)}">Apple / Outlook</a>
      <a class="btn" href="{e(gcal)}" target="_blank" rel="noopener">Google Calendar</a>
      <button class="btn ghost" type="button" data-copy="{e(ics_https)}">Copy feed URL</button>
    </div>
  </section>

  {_season_block(cur, now, current=True)}

  {prior}

  <footer>
    <p>Updated {e(updated)} from <a href="https://leagues.teamlinkt.com/{e(cfg['league_slug'])}/Schedule" target="_blank" rel="noopener">TeamLinkt</a> · <a href="data.json">data.json</a></p>
  </footer>
</main>
<script>
document.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', async () => {{
  try {{ await navigator.clipboard.writeText(b.dataset.copy); b.textContent = 'Copied!'; }}
  catch {{ prompt('Copy this URL', b.dataset.copy); }}
  setTimeout(() => b.textContent = 'Copy feed URL', 2000);
}}));
</script>
</body>
</html>
"""

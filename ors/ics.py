"""Minimal RFC 5545 calendar feed for the team's games."""

from __future__ import annotations

from datetime import datetime, timezone

from .model import Game


def _esc(s: str) -> str:
    return (
        s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold to 75 octets per RFC 5545 section 3.1."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_calendar(team: str, games: list[Game], *, site_url: str, now: datetime) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//macgillivary.dev//ors-soccer//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(team)}",
        "X-WR-TIMEZONE:America/Toronto",
        "REFRESH-INTERVAL;VALUE=DURATION:PT3H",
        "X-PUBLISHED-TTL:PT3H",
    ]
    for g in games:
        where = "vs" if g.side == "HOME" else "@"
        summary = f"⚽ {team} {where} {g.opponent}"
        if g.exhibition:
            summary += " (exhibition)"
        if g.played:
            us, them = (
                (g.home_score, g.away_score) if g.side == "HOME" else (g.away_score, g.home_score)
            )
            summary += f" — {g.result} {us}-{them}"
        desc = [f"{g.side.title()} vs {g.opponent}"]
        if g.kit.get("wear") and g.kit["wear"] != "?":
            desc.append(f"Wear: {g.kit['wear']} ({g.kit['reason']})")
        if g.map_url:
            desc.append(f"Map: {g.map_url}")
        if g.summary_url:
            desc.append(f"Game page: {g.summary_url}")
        desc.append(site_url)
        uid = f"teamlinkt-{g.event_id}" if g.event_id else f"{_utc(g.start)}-{g.opponent}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{_esc(uid)}@macgillivary.dev",
            f"DTSTAMP:{_utc(now)}",
            f"DTSTART:{_utc(g.start)}",
            f"DTEND:{_utc(g.end)}",
            f"SUMMARY:{_esc(summary)}",
            f"LOCATION:{_esc(g.location)}",
            f"DESCRIPTION:{_esc(chr(10).join(desc))}",
            f"URL:{g.summary_url or site_url}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"

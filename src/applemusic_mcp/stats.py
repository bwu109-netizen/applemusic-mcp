"""Pure-Python aggregation over a library snapshot (column arrays from JXA)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

UNKNOWN = "(unknown)"


def _local(iso: str | None) -> str | None:
    """JXA serializes dates as UTC ISO strings; show them in local time."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().isoformat()
    except ValueError:
        return iso


def to_rows(cols: dict[str, list]) -> list[dict[str, Any]]:
    keys = list(cols)
    n = len(cols[keys[0]]) if keys else 0
    rows = []
    for i in range(n):
        r = {k: cols[k][i] for k in keys}
        r["plays"] = r.get("plays") or 0
        r["artist"] = (r.get("artist") or "").strip() or UNKNOWN
        r["album"] = (r.get("album") or "").strip() or UNKNOWN
        r["genre"] = (r.get("genre") or "").strip() or UNKNOWN
        r["added"] = _local(r.get("added"))
        r["played"] = _local(r.get("played"))
        rows.append(r)
    return rows


def _track(r: dict) -> dict:
    return {k: r.get(k) for k in ("id", "name", "artist", "album", "plays")}


def overview(rows: list[dict]) -> dict:
    total_sec = sum(r.get("duration") or 0 for r in rows)
    played_sec = sum((r.get("duration") or 0) * r["plays"] for r in rows)
    never = sum(1 for r in rows if r["plays"] == 0)
    return {
        "tracks": len(rows),
        "artists": len({r["artist"] for r in rows}),
        "albums": len({(r["artist"], r["album"]) for r in rows}),
        "library_hours": round(total_sec / 3600, 1),
        "total_plays": sum(r["plays"] for r in rows),
        "estimated_listening_hours": round(played_sec / 3600, 1),
        "never_played_tracks": never,
        "top_artists": top_artists(rows, 5),
        "top_genres": top_genres(rows, 5),
    }


def top_tracks(rows: list[dict], limit: int) -> list[dict]:
    played = [r for r in rows if r["plays"] > 0]
    played.sort(key=lambda r: r["plays"], reverse=True)
    return [_track(r) for r in played[:limit]]


def _group(rows: list[dict], key) -> list[dict]:
    plays: Counter = Counter()
    tracks: Counter = Counter()
    for r in rows:
        k = key(r)
        plays[k] += r["plays"]
        tracks[k] += 1
    return [{"key": k, "plays": p, "tracks": tracks[k]} for k, p in plays.items()]


def top_artists(rows: list[dict], limit: int) -> list[dict]:
    g = _group(rows, lambda r: r["artist"])
    g.sort(key=lambda x: (x["plays"], x["tracks"]), reverse=True)
    return [{"artist": x["key"], "plays": x["plays"], "tracks": x["tracks"]} for x in g[:limit]]


def top_albums(rows: list[dict], limit: int) -> list[dict]:
    g = _group(rows, lambda r: (r["artist"], r["album"]))
    g.sort(key=lambda x: (x["plays"], x["tracks"]), reverse=True)
    return [
        {"album": x["key"][1], "artist": x["key"][0], "plays": x["plays"], "tracks": x["tracks"]}
        for x in g[:limit]
    ]


def top_genres(rows: list[dict], limit: int) -> list[dict]:
    total = sum(r["plays"] for r in rows) or 1
    g = _group(rows, lambda r: r["genre"])
    g.sort(key=lambda x: (x["plays"], x["tracks"]), reverse=True)
    return [
        {"genre": x["key"], "plays": x["plays"], "share": round(x["plays"] / total, 3),
         "tracks": x["tracks"]}
        for x in g[:limit]
    ]


def recently_added(rows: list[dict], limit: int) -> list[dict]:
    have = [r for r in rows if r.get("added")]
    have.sort(key=lambda r: r["added"], reverse=True)  # ISO strings sort chronologically
    return [{**_track(r), "added": r["added"][:10]} for r in have[:limit]]


def recently_played(rows: list[dict], limit: int) -> list[dict]:
    have = [r for r in rows if r.get("played")]
    have.sort(key=lambda r: r["played"], reverse=True)
    return [{**_track(r), "last_played": r["played"][:16].replace("T", " ")} for r in have[:limit]]


def artist_detail(rows: list[dict], artist: str, limit: int) -> dict:
    q = artist.casefold()
    mine = [r for r in rows if q in r["artist"].casefold()]
    albums: dict[str, int] = defaultdict(int)
    for r in mine:
        albums[r["album"]] += r["plays"]
    return {
        "matched_artists": sorted({r["artist"] for r in mine}),
        "tracks": len(mine),
        "plays": sum(r["plays"] for r in mine),
        "albums": sorted(({"album": a, "plays": p} for a, p in albums.items()),
                         key=lambda x: x["plays"], reverse=True),
        "top_tracks": top_tracks(mine, limit),
    }

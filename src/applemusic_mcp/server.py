"""Apple Music MCP server: control the macOS Music app and analyze your library."""

from __future__ import annotations

import time
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from . import jxa, stats

mcp = MCPServer(
    "apple-music",
    instructions=(
        "Controls the Apple Music app on this Mac and reads the user's library. "
        "Track ids are Music persistent IDs returned by search/playlist tools; pass them "
        "back to play_track / add_to_playlist. Search only covers the user's library, "
        "not the full Apple Music catalog."
    ),
)


# --------------------------------------------------------------------------- playback


@mcp.tool()
def now_playing() -> dict:
    """What's playing right now, plus player state, volume, shuffle and repeat."""
    return jxa.run("return playerSnapshot();")


@mcp.tool()
def playback(action: Literal["play", "pause", "toggle", "next", "previous", "stop"]) -> dict:
    """Control playback. Returns the player state afterwards."""
    return jxa.run(
        """
        const f = { play: () => Music.play(), pause: () => Music.pause(),
                    toggle: () => Music.playpause(), next: () => Music.nextTrack(),
                    previous: () => Music.previousTrack(), stop: () => Music.stop() };
        f[A.action]();
        delay(0.4);
        return playerSnapshot();
        """,
        {"action": action},
    )


@mcp.tool()
def set_player_options(
    volume: int | None = None,
    shuffle: bool | None = None,
    repeat: Literal["off", "one", "all"] | None = None,
) -> dict:
    """Set volume (0-100), shuffle on/off, and/or repeat mode. Omit what you don't want to change."""
    if volume is not None:
        volume = max(0, min(100, volume))
    return jxa.run(
        """
        if (A.volume !== null) Music.soundVolume = A.volume;
        if (A.shuffle !== null) Music.shuffleEnabled = A.shuffle;
        if (A.repeat !== null) Music.songRepeat = A.repeat;
        return playerSnapshot();
        """,
        {"volume": volume, "shuffle": shuffle, "repeat": repeat},
    )


# --------------------------------------------------------------------------- search

_SEARCH = """
let res = null;
try { res = Music.search(lib(), { for: A.query, only: A.kind }); } catch (e) { res = null; }
if (!res) {
  // Fallback: substring match on name / artist / album.
  const q = A.query;
  res = lib().tracks.whose({ _or: [
    { name: { _contains: q } }, { artist: { _contains: q } }, { album: { _contains: q } } ] })();
}
"""


@mcp.tool()
def search_library(
    query: str,
    kind: Literal["all", "songs", "artists", "albums"] = "all",
    limit: int = 20,
) -> dict:
    """Search the user's Music library. Returns tracks with ids you can play or add to playlists."""
    return jxa.run(
        _SEARCH + "return { total: res.length, tracks: res.slice(0, A.limit).map(trackInfo) };",
        {"query": query, "kind": kind, "limit": max(1, min(limit, 200))},
        timeout=60,
    )


@mcp.tool()
def play_track(track_id: str) -> dict:
    """Play a specific track by its id (from search_library or get_playlist_tracks)."""
    return jxa.run(
        "findTrack(A.id).play(); delay(0.4); return playerSnapshot();",
        {"id": track_id},
    )


@mcp.tool()
def search_and_play(
    query: str, kind: Literal["all", "songs", "artists", "albums"] = "all"
) -> dict:
    """Search the library and immediately play the best match. Also returns other candidates."""
    return jxa.run(
        _SEARCH
        + """
        if (res.length === 0) throw new Error('No match in library for: ' + A.query);
        res[0].play();
        delay(0.4);
        return { now_playing: playerSnapshot(), other_matches: res.slice(1, 6).map(trackInfo) };
        """,
        {"query": query, "kind": kind},
        timeout=60,
    )


# --------------------------------------------------------------------------- playlists


@mcp.tool()
def list_playlists() -> list[dict]:
    """List the user's own playlists (regular and smart), with track counts."""
    return jxa.run(
        """
        const ps = Music.userPlaylists;
        if (ps.length === 0) return [];
        const names = ps.name(), ids = ps.persistentID(), kinds = ps.specialKind(),
              smart = ps.smart(), durs = ps.duration();
        const all = ps();
        const out = [];
        for (let i = 0; i < names.length; i++) {
          if (kinds[i] !== 'none') continue;  // skip folders and built-in lists
          out.push({ name: names[i], id: ids[i], smart: smart[i],
                     tracks: safe(() => all[i].tracks.length, null),
                     minutes: Math.round((durs[i] || 0) / 60) });
        }
        return out;
        """,
        timeout=60,
    )


@mcp.tool()
def get_playlist_tracks(playlist: str, limit: int = 100) -> dict:
    """List tracks in a playlist (by exact name)."""
    return jxa.run(
        "return bulkTracks(findPlaylist(A.name).tracks, A.limit);",
        {"name": playlist, "limit": max(1, min(limit, 1000))},
        timeout=60,
    )


@mcp.tool()
def play_playlist(playlist: str, shuffle: bool | None = None) -> dict:
    """Start playing a playlist by name, optionally setting shuffle first."""
    return jxa.run(
        """
        const p = findPlaylist(A.name);
        if (A.shuffle !== null) Music.shuffleEnabled = A.shuffle;
        p.play();
        delay(0.4);
        return playerSnapshot();
        """,
        {"name": playlist, "shuffle": shuffle},
    )


@mcp.tool()
def create_playlist(name: str, description: str | None = None) -> dict:
    """Create a new empty playlist. Fails if one with that name already exists."""
    return jxa.run(
        """
        if (Music.userPlaylists.whose({ name: A.name })().length > 0)
          throw new Error('A playlist named "' + A.name + '" already exists');
        const p = Music.make({ new: 'userPlaylist', withProperties: { name: A.name } });
        if (A.description) { try { p.description = A.description; } catch (e) {} }
        return { created: p.name(), id: p.persistentID() };
        """,
        {"name": name, "description": description},
    )


@mcp.tool()
def add_to_playlist(playlist: str, track_ids: list[str]) -> dict:
    """Add tracks (by id) to a playlist. Tracks already in the playlist are skipped."""
    return jxa.run(
        """
        const p = findPlaylist(A.name);
        if (safe(() => p.smart(), false)) throw new Error('Cannot add tracks to a smart playlist');
        const have = new Set(col(p.tracks, 'persistentID'));
        const added = [], skipped = [], failed = [];
        for (const id of A.ids) {
          if (have.has(id)) { skipped.push(id); continue; }
          try { Music.duplicate(findTrack(id), { to: p }); added.push(id); have.add(id); }
          catch (e) { failed.push({ id: id, error: String(e.message || e) }); }
        }
        return { playlist: A.name, added: added.length, skipped_existing: skipped.length, failed: failed };
        """,
        {"name": playlist, "ids": track_ids},
        timeout=120,
    )


@mcp.tool()
def remove_from_playlist(playlist: str, track_ids: list[str]) -> dict:
    """Remove tracks (by id) from a playlist. Does not delete them from the library."""
    return jxa.run(
        """
        const p = findPlaylist(A.name);
        if (safe(() => p.smart(), false)) throw new Error('Cannot edit a smart playlist');
        let removed = 0; const missing = [];
        for (const id of A.ids) {
          const hits = p.tracks.whose({ persistentID: id })();
          if (hits.length === 0) { missing.push(id); continue; }
          for (const t of hits) { Music.delete(t); removed++; }
        }
        return { playlist: A.name, removed: removed, not_in_playlist: missing };
        """,
        {"name": playlist, "ids": track_ids},
        timeout=120,
    )


# --------------------------------------------------------------------------- favorites


@mcp.tool()
def set_favorite(track_ids: list[str], favorite: bool = True, gap_sec: float = 0) -> dict:
    """Mark (or unmark) tracks as Favorite, one at a time in the given order.

    gap_sec waits between tracks so each gets a distinct timestamp. Keep calls under
    ~40 tracks when using a gap so the call doesn't time out.
    """
    return jxa.run(
        """
        let changed = 0, already = 0; const failed = [];
        for (let i = 0; i < A.ids.length; i++) {
          try {
            const t = findTrack(A.ids[i]);
            if (isFav(t) === A.fav) { already++; continue; }
            if (changed > 0 && A.gap > 0) delay(A.gap);
            setFav(t, A.fav); changed++;
          } catch (e) { failed.push({ id: A.ids[i], error: String(e.message || e) }); }
        }
        return { changed: changed, already: already, failed: failed };
        """,
        {"ids": track_ids, "fav": favorite, "gap": max(0.0, gap_sec)},
        timeout=60 + len(track_ids) * (gap_sec + 1),
    )


@mcp.tool()
def favorite_playlist(
    playlist: str,
    start: int = 0,
    count: int = 100,
    reverse: bool = True,
    gap_sec: float = 0,
) -> dict:
    """Mark a playlist's tracks as Favorite one by one, in batches.

    With reverse=true it walks from the LAST track toward the first. `start` is the
    position in that walking order; call again with the returned next_start until
    done=true. Tracks already favorited are skipped (keeps their earlier timestamp).
    gap_sec (default 0) optionally spaces out timestamps if the Music app's
    timestamps turn out to be too coarse to keep the order.
    """
    count = max(1, min(count, 500))
    return jxa.run(
        """
        const p = findPlaylist(A.name);
        const items = p.tracks();
        const n = items.length;
        if (n === 0) return { playlist: A.name, total: 0, processed: 0, favorited: [],
                              skipped_already_favorite: [], failed: [], next_start: 0, done: true };
        const order = [];
        for (let i = 0; i < n; i++) order.push(A.reverse ? n - 1 - i : i);
        const end = Math.min(n, A.start + A.count);
        const names = p.tracks.name();
        const done = [], skipped = [], failed = [];
        let changed = 0;
        for (let k = A.start; k < end; k++) {
          const idx = order[k], t = items[idx];
          try {
            if (isFav(t)) { skipped.push(names[idx]); continue; }
            if (changed > 0 && A.gap > 0) delay(A.gap);
            setFav(t, true); changed++;
            done.push((idx + 1) + '. ' + names[idx]);
          } catch (e) { failed.push({ position: idx + 1, name: names[idx], error: String(e.message || e) }); }
        }
        return { playlist: A.name, total: n, processed: end - A.start, favorited: done,
                 skipped_already_favorite: skipped, failed: failed,
                 next_start: end, done: end >= n };
        """,
        {"name": playlist, "start": max(0, start), "count": count, "reverse": reverse,
         "gap": max(0.0, gap_sec)},
        timeout=60 + count * (gap_sec + 1),
    )


@mcp.tool()
def compare_playlists(playlist: str, against: list[str], limit: int = 200) -> dict:
    """Tracks in `playlist` that are NOT in any of the `against` playlists (read-only)."""
    return jxa.run(
        """
        const others = new Set();
        for (const name of A.against)
          for (const id of col(findPlaylist(name).tracks, 'persistentID')) others.add(id);
        const p = findPlaylist(A.name);
        const ids = col(p.tracks, 'persistentID'), names = col(p.tracks, 'name'),
              artists = col(p.tracks, 'artist');
        const only = [];
        for (let i = 0; i < ids.length; i++)
          if (!others.has(ids[i])) only.push({ id: ids[i], name: names[i], artist: artists[i] });
        return { playlist: A.name, total: ids.length, not_in_others: only.length,
                 tracks: only.slice(0, A.limit) };
        """,
        {"name": playlist, "against": against, "limit": max(1, min(limit, 1000))},
        timeout=90,
    )


# --------------------------------------------------------------------------- stats

_CACHE: dict[str, Any] = {"at": 0.0, "rows": None}
_CACHE_TTL = 300  # seconds

_FETCH_LIBRARY = """
const t = lib().tracks;
if (t.length === 0) return { id: [], name: [], artist: [], album: [], genre: [], plays: [],
                             played: [], added: [], duration: [] };
return { id: t.persistentID(), name: t.name(), artist: t.artist(), album: t.album(),
         genre: t.genre(), plays: t.playedCount(), played: t.playedDate(),
         added: t.dateAdded(), duration: t.duration() };
"""


def _library_rows(refresh: bool = False) -> list[dict]:
    if refresh or _CACHE["rows"] is None or time.time() - _CACHE["at"] > _CACHE_TTL:
        cols = jxa.run(_FETCH_LIBRARY, timeout=180)
        _CACHE["rows"] = stats.to_rows(cols)
        _CACHE["at"] = time.time()
    return _CACHE["rows"]


@mcp.tool()
def listening_stats(
    view: Literal[
        "overview", "top_tracks", "top_artists", "top_albums", "top_genres",
        "recently_added", "recently_played",
    ] = "overview",
    limit: int = 20,
    refresh: bool = False,
) -> Any:
    """Analyze the library: play counts, favorite artists/albums/genres, recent activity.

    Play counts are lifetime totals tracked by the Music app (no per-period history).
    Library data is cached for 5 minutes; pass refresh=true to re-read it.
    """
    rows = _library_rows(refresh)
    limit = max(1, min(limit, 200))
    if view == "overview":
        return stats.overview(rows)
    return getattr(stats, view)(rows, limit)


@mcp.tool()
def artist_stats(artist: str, limit: int = 10) -> dict:
    """Everything about one artist in the library: track count, total plays, albums, top songs."""
    return stats.artist_detail(_library_rows(), artist, max(1, min(limit, 100)))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

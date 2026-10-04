"""Off-Mac tests: tool plumbing, JXA syntax, and stats. No Music app needed."""

import asyncio
import json
import shutil
import subprocess

import pytest

from applemusic_mcp import jxa, server, stats

CAPTURED: list[tuple[str, dict]] = []

FAKE_LIB = {
    "id": ["A1", "A2", "A3", "A4"],
    "name": ["晴天", "七里香", "Blinding Lights", "Untitled"],
    "artist": ["周杰伦", "周杰伦", "The Weeknd", ""],
    "album": ["叶惠美", "七里香", "After Hours", ""],
    "genre": ["Mandopop", "Mandopop", "Pop", None],
    "plays": [120, 80, 50, 0],
    "played": ["2026-10-01T03:00:00.000Z", "2026-09-30T03:00:00.000Z", "2026-10-02T03:00:00.000Z", None],
    "added": ["2020-01-01T00:00:00.000Z", "2021-01-01T00:00:00.000Z", "2026-09-01T00:00:00.000Z", "2026-09-02T00:00:00.000Z"],
    "duration": [269.0, 299.0, 200.0, 100.0],
}


@pytest.fixture(autouse=True)
def fake_run(monkeypatch):
    CAPTURED.clear()
    server._CACHE.update(at=0.0, rows=None)

    def fake(body, args=None, timeout=30):
        CAPTURED.append((body, args or {}))
        if "playedCount" in body:
            return FAKE_LIB
        return [] if "userPlaylists;" in body else {"ok": True}

    monkeypatch.setattr(jxa, "run", fake)


def call(tool, **kw):
    return asyncio.run(server.mcp.call_tool(tool, kw))


def test_tools_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {
        "now_playing", "playback", "set_player_options", "search_library", "play_track",
        "search_and_play", "list_playlists", "get_playlist_tracks", "play_playlist",
        "create_playlist", "add_to_playlist", "remove_from_playlist",
        "listening_stats", "artist_stats",
        "set_favorite", "favorite_playlist", "compare_playlists",
    }


ALL_CALLS = [
    ("now_playing", {}),
    ("playback", {"action": "next"}),
    ("set_player_options", {"volume": 150, "shuffle": True}),
    ("search_library", {"query": 'he said "hi"', "kind": "songs"}),
    ("play_track", {"track_id": "ABC"}),
    ("search_and_play", {"query": "周杰伦"}),
    ("list_playlists", {}),
    ("get_playlist_tracks", {"playlist": "Gym"}),
    ("play_playlist", {"playlist": "Gym", "shuffle": True}),
    ("create_playlist", {"name": "New"}),
    ("add_to_playlist", {"playlist": "Gym", "track_ids": ["A1"]}),
    ("remove_from_playlist", {"playlist": "Gym", "track_ids": ["A1"]}),
    ("listening_stats", {"view": "overview"}),
    ("set_favorite", {"track_ids": ["A1", "A2"], "gap_sec": 1}),
    ("favorite_playlist", {"playlist": "3", "start": 0, "count": 5}),
    ("compare_playlists", {"playlist": "喜爱歌曲", "against": ["1", "2", "3"]}),
]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
@pytest.mark.parametrize("name,kw", ALL_CALLS)
def test_jxa_scripts_parse(name, kw, tmp_path):
    call(name, **kw)
    assert CAPTURED, "tool did not call jxa.run"
    for body, args in CAPTURED:
        f = tmp_path / "s.js"
        f.write_text(jxa.build_script(body))
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        json.dumps(args)  # args must be JSON-serializable


def test_user_input_not_in_source():
    call("search_library", query='x"); Music.quit(); ("')
    body, args = CAPTURED[0]
    assert "Music.quit" not in body
    assert args["query"].startswith('x"')


def test_volume_clamped():
    call("set_player_options", volume=150)
    assert CAPTURED[0][1]["volume"] == 100


def test_stats():
    rows = stats.to_rows(FAKE_LIB)
    ov = stats.overview(rows)
    assert ov["tracks"] == 4 and ov["total_plays"] == 250 and ov["never_played_tracks"] == 1
    assert stats.top_artists(rows, 1)[0] == {"artist": "周杰伦", "plays": 200, "tracks": 2}
    assert [t["id"] for t in stats.top_tracks(rows, 10)] == ["A1", "A2", "A3"]
    assert stats.recently_added(rows, 1)[0]["id"] == "A4"
    assert stats.recently_played(rows, 1)[0]["id"] == "A3"
    assert stats.top_genres(rows, 1)[0]["genre"] == "Mandopop"
    assert stats.artist_detail(rows, "周", 5)["plays"] == 200


def test_stats_tool_caches():
    call("listening_stats", view="top_artists")
    call("listening_stats", view="top_genres")
    assert len(CAPTURED) == 1


def test_error_cleanup():
    assert jxa._clean_error("execution error: Error: Playlist not found: Gym (-2700)") == "Playlist not found: Gym"
    assert "Automation" in jxa._clean_error("execution error: Not authorized to send Apple events to Music. (-1743)")


def test_music_error_reaches_client(monkeypatch):
    def boom(body, args=None, timeout=30):
        raise jxa.MusicError("Playlist not found: Gym")

    monkeypatch.setattr(jxa, "run", boom)
    with pytest.raises(Exception, match="Playlist not found: Gym"):
        call("get_playlist_tracks", playlist="Gym")

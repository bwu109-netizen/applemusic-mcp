"""Run JavaScript for Automation (JXA) against the macOS Music app.

User input is never pasted into script source. It is passed as a JSON string
in argv and parsed inside the script, so song names with quotes etc. are safe.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

# Helpers available to every script body.
PRELUDE = r"""
const Music = Application('Music');
function safe(f, d) { try { const v = f(); return v === undefined ? d : v; } catch (e) { return d; } }
function lib() { return Music.libraryPlaylists[0]; }
// Newer macOS calls it `favorited`; older versions call it `loved`.
function isFav(t) { try { return t.favorited(); } catch (e) { return t.loved(); } }
function setFav(t, v) { try { t.favorited = v; } catch (e) { t.loved = v; } }
function trackInfo(t) {
  return {
    id: safe(() => t.persistentID(), null),
    name: safe(() => t.name(), ''),
    artist: safe(() => t.artist(), ''),
    album: safe(() => t.album(), ''),
    genre: safe(() => t.genre(), ''),
    duration_sec: Math.round(safe(() => t.duration(), 0)),
  };
}
// Bulk-read one property of every element: one Apple Event instead of one per item.
// Reading a property of an EMPTY collection throws "Can't get object", so guard it.
function col(spec, prop) { return spec.length === 0 ? [] : spec[prop](); }
function bulkTracks(spec, limit) {
  const ids = col(spec, 'persistentID');
  const n = Math.min(ids.length, limit);
  if (n === 0) return { total: ids.length, tracks: [] };
  const names = spec.name(), artists = spec.artist(), albums = spec.album(), durs = spec.duration();
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push({ id: ids[i], name: names[i], artist: artists[i], album: albums[i],
               duration_sec: Math.round(durs[i] || 0) });
  }
  return { total: ids.length, tracks: out };
}
function findTrack(id) {
  const r = lib().tracks.whose({ persistentID: id })();
  if (r.length === 0) throw new Error('Track not found: ' + id);
  return r[0];
}
function findPlaylist(name) {
  const r = Music.userPlaylists.whose({ name: name })();
  if (r.length === 0) throw new Error('Playlist not found: ' + name);
  return r[0];
}
function playerSnapshot() {
  if (!Music.running()) return { state: 'not_running' };
  const st = Music.playerState();
  const out = {
    state: st,
    volume: safe(() => Music.soundVolume(), null),
    shuffle: safe(() => Music.shuffleEnabled(), null),
    repeat: safe(() => Music.songRepeat(), null),
  };
  if (st !== 'stopped') {
    const t = Music.currentTrack;
    out.track = trackInfo(t);
    out.position_sec = Math.round(safe(() => Music.playerPosition(), 0));
    const stream = safe(() => Music.currentStreamTitle(), null);
    if (stream) out.stream_title = stream;
  }
  return out;
}
"""

PERMISSION_HINT = (
    "macOS has not allowed this app to control Music. Open System Settings > "
    "Privacy & Security > Automation, find Claude (or your terminal), and turn on 'Music'."
)


class MusicError(ToolError):
    """Raised when the Music app or osascript reports an error.

    Subclassing ToolError makes MCP send the message to the client instead of
    hiding it as an internal crash.
    """


def build_script(body: str) -> str:
    return (
        "function run(argv) {\n"
        + PRELUDE
        + "\nconst A = JSON.parse(argv[0] || '{}');\n"
        + "const __r = (function () {\n"
        + body
        + "\n})();\n"
        + "return JSON.stringify(__r === undefined ? null : __r);\n}\n"
    )


def _clean_error(stderr: str) -> str:
    msg = stderr.strip()
    if "-1743" in msg or "Not authorized" in msg:
        return PERMISSION_HINT
    # osascript format: "execution error: Error: Track not found: X (-2700)"
    m = re.search(r"execution error: (?:Error: )?(.*?)(?: \(-?\d+\))?$", msg, re.S)
    return (m.group(1) if m else msg) or "Unknown osascript error"


def run(body: str, args: dict[str, Any] | None = None, timeout: float = 30) -> Any:
    """Run a JXA body (which should `return` a JSON-able value) and parse the result."""
    script = build_script(body)
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script, json.dumps(args or {})],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise MusicError("osascript not found. This server only works on macOS.") from e
    except subprocess.TimeoutExpired as e:
        raise MusicError(f"Music app did not respond within {timeout:.0f}s.") from e

    if proc.returncode != 0:
        raise MusicError(_clean_error(proc.stderr))
    out = proc.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out

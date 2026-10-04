# applemusic-mcp

[![CI](https://github.com/bwu109-netizen/applemusic-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/bwu109-netizen/applemusic-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

English | [简体中文](README.zh-CN.md)

An [MCP](https://modelcontextprotocol.io) server that lets Claude (or any MCP client) control the **Music app on macOS** and analyze your library. Just talk to it:

> "Play some Leehom Wang"
> "Make a playlist of the K-pop songs in my library"
> "What genres do I listen to most?"
> "Favorite every song in playlists 3, 2, 1, last track first, so Favorite Songs shows them in order"

Everything runs locally on your Mac through JavaScript for Automation (JXA). No Apple Developer account, no API keys, and nothing leaves your machine.

## Features

| Area | Tools |
|---|---|
| Playback | `now_playing`, `playback` (play / pause / toggle / next / previous / stop), `set_player_options` (volume, shuffle, repeat) |
| Search | `search_library`, `search_and_play`, `play_track` |
| Playlists | `list_playlists`, `get_playlist_tracks`, `play_playlist`, `create_playlist`, `add_to_playlist`, `remove_from_playlist`, `compare_playlists` |
| Favorites | `set_favorite`, `favorite_playlist` (in order, in batches, optional gap so "sort by Date Favorited" keeps your order) |
| Stats | `listening_stats` (overview, top tracks / artists / albums / genres, recently added / played), `artist_stats` |

**Limits:** search covers your library, not the full Apple Music catalog. Play counts are the lifetime totals the Music app keeps on this Mac, so there's no per-week history. If you mostly listen on your phone, counts may be low.

## Requirements

- macOS with the Music app (tested on a recent macOS, Apple Silicon)
- [Claude Desktop](https://claude.ai/download) or another MCP client
- [uv](https://docs.astral.sh/uv/). The installer sets it up for you.

## Install

### One-click

1. Download or clone this repo, e.g. into `~/Documents/applemusic-mcp`.
2. Double-click **`install.command`**. If macOS blocks it, right-click > Open.
   It installs uv, runs a read-only self-test, and adds the server to Claude Desktop's config (it backs up the old config first).
3. When macOS asks whether the app may control Music, click **OK**.
4. Quit Claude Desktop with Cmd+Q, reopen it, and ask *"What's playing?"*

### Manual

```bash
git clone https://github.com/bwu109-netizen/applemusic-mcp.git
cd applemusic-mcp
uv sync
uv run python scripts/smoke_test.py   # read-only check
```

Then add this to `~/Library/Application Support/Claude/claude_desktop_config.json`, using your own paths (`which uv`):

```json
{
  "mcpServers": {
    "apple-music": {
      "command": "/Users/you/.local/bin/uv",
      "args": ["run", "--directory", "/Users/you/applemusic-mcp", "python", "-m", "applemusic_mcp.server"],
      "env": { "PYTHONPATH": "/Users/you/applemusic-mcp/src" }
    }
  }
}
```

## Troubleshooting

- **"Not authorized to send Apple events"**: open System Settings > Privacy & Security > Automation and turn on **Music** for Claude (or your terminal).
- **Server keeps disconnecting / `No module named applemusic_mcp`**: if the project lives in an iCloud-synced folder like Documents, iCloud can break a `.venv` inside it. `install.command` keeps the venv in `~/.local/share/applemusic-mcp/venv` instead. Re-run it.
- **Changes to the code don't show up**: Claude Desktop starts the server once. Quit it with Cmd+Q and reopen.

## How it works

```
Claude ──MCP (stdio)──▶ server.py ──osascript -l JavaScript──▶ Music.app
```

- `src/applemusic_mcp/jxa.py` runs JXA via `osascript`. User input is passed as JSON in `argv`, never pasted into script source, so song titles with quotes can't break or inject code. Errors come back as readable MCP tool errors.
- `src/applemusic_mcp/server.py` defines the tools. Library reads use bulk property fetches (one Apple Event per property, not per track), so even large libraries stay fast.
- `src/applemusic_mcp/stats.py` is plain Python aggregation over a 5-minute library cache.

## Development

```bash
uv sync
uv run pytest
```

The tests mock the Music app, so they run on Linux too (CI uses Ubuntu). They also run `node --check` on every generated JXA script to catch syntax errors before they reach a Mac.

PRs welcome. Ideas: Apple Music catalog search via MusicKit, AirPlay device selection, ratings, smart-playlist creation.

## License

[MIT](LICENSE)

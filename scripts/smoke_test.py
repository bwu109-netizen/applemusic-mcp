"""Read-only check against the real Music app. Run on your Mac:

    uv run python scripts/smoke_test.py

It doesn't play, pause or edit anything. The first run triggers a macOS
prompt asking to allow control of Music; click Allow.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from applemusic_mcp import server  # noqa: E402

CHECKS = [
    ("now_playing", lambda: server.now_playing()),
    ("list_playlists", lambda: server.list_playlists()[:5]),
    ("search_library('love')", lambda: server.search_library("love", limit=3)),
    ("listening_stats overview", lambda: server.listening_stats("overview")),
    ("listening_stats top_tracks", lambda: server.listening_stats("top_tracks", limit=5)),
]

ok = 0
for label, fn in CHECKS:
    t = time.time()
    try:
        out = fn()
        ok += 1
        print(f"PASS {label} ({time.time() - t:.1f}s)")
        print(json.dumps(out, ensure_ascii=False, indent=2)[:800], "\n")
    except Exception as e:
        print(f"FAIL {label}: {e}\n")
print(f"{ok}/{len(CHECKS)} passed")
sys.exit(0 if ok == len(CHECKS) else 1)

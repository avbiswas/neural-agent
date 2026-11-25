"""Serve the agent's sites (agent/sites/) on 127.0.0.1:8080.

    uv run sites.py
    tailscale serve --bg 8080    # once: makes it https://<your-mac>.<tailnet>.ts.net/

127.0.0.1 means nothing else on your network can reach it. Tailscale Serve
forwards to it, so only devices on your tailnet can open the pages.
"""
import functools
import http.server
from pathlib import Path

SITES = Path(__file__).parent / "agent" / "sites"
SITES.mkdir(parents=True, exist_ok=True)

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SITES)
print("sites: serving agent/sites/ on http://127.0.0.1:8080")
http.server.ThreadingHTTPServer(("127.0.0.1", 8080), handler).serve_forever()

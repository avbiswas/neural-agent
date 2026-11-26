"""Serve the agent's sites (agent/sites/) on 127.0.0.1:8080.

    uv run sites.py
    tailscale serve --bg 8080    # once, on the server: https://<server>.<tailnet>.ts.net/

127.0.0.1 means nothing else on your network can reach it. Tailscale Serve
forwards to it, so only devices on your tailnet can open the pages.
"""
import functools
import http.server
import os
from pathlib import Path

SITES = Path(__file__).parent / "agent" / "sites"
SITES.mkdir(parents=True, exist_ok=True)

HOST = os.environ.get("SITES_HOST", "127.0.0.1")  # 0.0.0.0 inside Docker; compose publishes it on 127.0.0.1

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SITES)
print(f"sites: serving agent/sites/ on http://{HOST}:8080")
http.server.ThreadingHTTPServer((HOST, 8080), handler).serve_forever()

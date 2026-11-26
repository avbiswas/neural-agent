"""The secrets page: where you add, replace and delete the keys your agent may
use (API tokens for Fly, Vercel...). A harness service, not one of the agent's
sites, on its own port, so no page the agent writes can reach it.

    uv run python -m web.secrets_page
    tailscale serve --bg --https 8443 8081    # once: https://<server>.<tailnet>.ts.net:8443/

It never shows a value, only which secrets exist. The agent asks for missing
ones with a link like /?ask=FLY_API_TOKEN, and uses them through `with-secrets`.
"""
import html
import http.server
import os
import re
import secrets
import urllib.parse
from datetime import datetime
from pathlib import Path

SECRETS = Path(os.environ.get("SECRETS_DIR", "/run/agent-secrets"))  # one file per secret
HOST = os.environ.get("SECRETS_HOST", "127.0.0.1")
NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")   # what an environment variable may be called
FORM_TOKEN = secrets.token_urlsafe(16)          # only forms from this page may change secrets


def page(ask):
    rows = "".join(f"""<tr><td><code>{p.name}</code></td>
        <td>set {datetime.fromtimestamp(p.stat().st_mtime):%d %b %H:%M}</td>
        <td>{field(p.name, "Replace")}</td>
        <td><form method="post"><input type="hidden" name="token" value="{FORM_TOKEN}">
            <input type="hidden" name="delete" value="{p.name}"><button>Delete</button></form></td></tr>"""
        for p in sorted(SECRETS.iterdir()))
    asked = "".join(f"<p><b><code>{n}</code></b> {field(n, 'Save')}</p>" for n in ask if NAME.match(n))
    return f"""<!doctype html><title>Secrets</title>
<body style="font: 15px system-ui; max-width: 50em; margin: 3em auto">
<h1>Secrets</h1>
{f'<h2>Your agent asked for</h2>{asked}' if asked else ''}
<h2>Saved</h2><table cellpadding="6">{rows or '<tr><td>None yet.</td></tr>'}</table>
<h2>Add one</h2>
<form method="post"><input type="hidden" name="token" value="{FORM_TOKEN}">
<input name="name" placeholder="NAME (e.g. MY_API_KEY)" pattern="[A-Z][A-Z0-9_]*">
<input name="value" type="password" placeholder="value" autocomplete="off"> <button>Save</button></form>"""


def field(name, label):
    return f"""<form method="post" style="display:inline"><input type="hidden" name="token" value="{FORM_TOKEN}">
        <input type="hidden" name="name" value="{name}">
        <input name="value" type="password" placeholder="value" autocomplete="off"> <button>{label}</button></form>"""


class Secrets(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        ask = ",".join(query.get("ask", [])).split(",")
        self.reply(page([n for n in ask if n and not (SECRETS / n).exists()]))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode()).items()}
        if form.get("token") != FORM_TOKEN:
            return self.reply("This form is out of date. Reload the page.", 403)
        if NAME.match(form.get("delete", "")):
            (SECRETS / form["delete"]).unlink(missing_ok=True)
            print(f"secrets: deleted {form['delete']}")
        elif NAME.match(form.get("name", "")) and form.get("value", "").strip():
            path = SECRETS / form["name"]
            path.write_text(form["value"].strip())
            path.chmod(0o600)
            print(f"secrets: saved {form['name']}")   # the name only, never the value
        self.send_response(303)                       # back to the list
        self.send_header("Location", "/")
        self.end_headers()

    def reply(self, body, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())


SECRETS.mkdir(parents=True, exist_ok=True)
print(f"secrets: serving on http://{HOST}:8081")
http.server.ThreadingHTTPServer((HOST, 8081), Secrets).serve_forever()

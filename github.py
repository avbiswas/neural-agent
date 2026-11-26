"""GitHub access through a GitHub App that you own: the way Vercel or a CI
service connects to your repos. You pick which repos it may use, on GitHub.
The app's private key stays with the harness (data/, which the agent never
sees); when the harness needs GitHub, it mints a token that lasts one hour and
reaches only the repos and permissions it asks for.

One-time setup: create the app, then install it on your repos.

    docker compose run --rm --service-ports github-setup
    # then open http://localhost:8090
    # (on a server, tunnel the port first: ssh -L 8090:localhost:8090 you@server)
"""
import html
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import jwt

APP_FILE = Path(__file__).parent / "data" / "github-app.json"  # the app's id and private key
PORT = 8090
SETUP_URL = f"http://localhost:{PORT}"


def api(method, path, token=None, body=None):
    """Call the GitHub REST API and return the JSON reply."""
    request = urllib.request.Request(
        "https://api.github.com" + path, method=method,
        data=json.dumps(body or {}).encode() if method != "GET" else None,
        headers={"Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def load_app():
    """The app, once setup has created and installed it (else None)."""
    app = json.loads(APP_FILE.read_text()) if APP_FILE.exists() else {}
    return app if "installation_id" in app else None


def save_app(app):
    APP_FILE.parent.mkdir(parents=True, exist_ok=True)
    APP_FILE.write_text(json.dumps(app, indent=2))
    APP_FILE.chmod(0o600)


def token(app, repos=None, permissions=None):
    """An installation token: valid one hour, for these repos and permissions
    only (or everything the installation has). The app signs a short JWT with
    its private key to prove who it is, and GitHub swaps that for the token."""
    now = int(time.time())
    app_jwt = jwt.encode({"iat": now - 60, "exp": now + 540, "iss": app["client_id"]},
                         app["pem"], algorithm="RS256")
    limits = {"repositories": repos, "permissions": permissions}
    reply = api("POST", f"/app/installations/{app['installation_id']}/access_tokens", app_jwt,
                {key: value for key, value in limits.items() if value})
    return reply["token"]


# --- one-time setup: GitHub's "app manifest" flow ---------------------------
# 1. Our page posts a manifest (the app's settings) to GitHub.
# 2. You click "Create GitHub App"; GitHub sends you back to /created?code=...
# 3. We swap the code for the app's id and private key, then send you on to
#    install the app. GitHub sends you back to /installed?installation_id=...

STATE = secrets.token_urlsafe(16)  # proves the redirect answers our own request
MANIFEST = {
    "name": f"agent-{secrets.token_hex(3)}",  # app names are global: rename it if you like
    "description": "My always-on agent's access to my repos.",
    "url": SETUP_URL,
    "redirect_url": f"{SETUP_URL}/created",
    "setup_url": f"{SETUP_URL}/installed",
    "public": False,                           # only your account can install it
    "default_permissions": {"contents": "write", "metadata": "read"},
    "hook_attributes": {"url": "https://example.com/", "active": False},  # no webhooks
}
SETUP_PAGE = f"""<!doctype html><title>Connect GitHub</title>
<body style="font: 16px system-ui; max-width: 36em; margin: 4em auto">
<h1>Connect your agent to GitHub</h1>
<p>First create an empty private repo for the agent's backup, e.g.
<b>agent-workspace</b>. This page then creates a private GitHub App for your
agent, and GitHub asks which repos it may use: pick that repo.</p>
<form method="post" action="https://github.com/settings/apps/new?state={STATE}">
<input type="hidden" name="manifest" value="{html.escape(json.dumps(MANIFEST))}">
<button style="font-size: 1.1em">Create GitHub App</button></form>"""


class Setup(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path == "/":
            self.reply(200, SETUP_PAGE)
        elif url.path == "/created" and query.get("state") == STATE:
            app = api("POST", f"/app-manifests/{query['code']}/conversions")
            save_app({"id": app["id"], "client_id": app["client_id"], "slug": app["slug"],
                      "owner": app["owner"]["login"], "pem": app["pem"]})
            print(f"github: created app {app['slug']}")
            self.send_response(302)
            self.send_header("Location", f"https://github.com/apps/{app['slug']}/installations/new")
            self.end_headers()
        elif url.path == "/installed" and "installation_id" in query:
            app = {**json.loads(APP_FILE.read_text()), "installation_id": int(query["installation_id"])}
            # The repo you picked is where the backup goes.
            repos = api("GET", "/installation/repositories", token(app))["repositories"]
            app["backup_repo"] = repos[0]["name"]
            save_app(app)
            print(f"github: installed, backing up to {app['owner']}/{app['backup_repo']}. Done.")
            self.reply(200, f"<h1>Done.</h1><p>Your agent backs up to <b>{app['owner']}/{app['backup_repo']}</b>. "
                            "You can close this tab.</p>")
            threading.Thread(target=self.server.shutdown).start()
        else:
            self.reply(400, "Unexpected request. Start again from the first page.")

    def reply(self, status, page):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode())


if __name__ == "__main__":
    host = os.environ.get("SETUP_HOST", "127.0.0.1")  # 0.0.0.0 inside Docker
    print(f"github: open {SETUP_URL} in your browser")
    http.server.HTTPServer((host, PORT), Setup).serve_forever()

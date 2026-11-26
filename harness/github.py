"""GitHub access through a GitHub App that you own: the way Vercel or a CI
service connects to your repos. You pick which repos it may use, on GitHub.
The app's private key stays with the harness (data/, which the agent never
sees); when the harness needs GitHub, it mints a token that lasts one hour and
reaches only the repos and permissions it asks for.

One-time setup: create the app, then install it on your repos. ./setup does
this step for you (see onboarding/wizard.py); on its own:

    uv run python -m harness.github     # then open http://localhost:8090/github
"""
import html
import http.server
import json
import os
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import jwt

APP_FILE = Path(__file__).parents[1] / "data" / "github-app.json"  # the app's id and private key
PORT = 8090                                          # inside the container
SETUP_URL = f"http://localhost:{os.environ.get('SETUP_PORT', PORT)}"  # in your browser


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
    if os.getuid() == 0:  # written by ./setup (root): hand it to the harness's user
        os.chown(APP_FILE, 1000, 1000)


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


def pick_repos(app):
    """(workspace repo, chat-log repo), out of the repos you gave the app.
    The chat log goes to the one whose name ends in -history or -chats."""
    names = [r["name"] for r in api("GET", "/installation/repositories?per_page=100", token(app))["repositories"]]
    history = next((name for name in names if name.endswith(("-history", "-chats"))), None)
    others = [name for name in names if name != history]
    workspace = app.get("backup_repo") if app.get("backup_repo") in others else (others[0] if len(others) == 1 else None)
    return workspace, history


def push(app, git_dir, repo):
    """Push main from one of the harness's own repos to <you>/<repo>, and say
    how it went. Never forced: if history was rewritten, GitHub refuses."""
    try:
        repo_token = token(app, [repo], {"contents": "write"})
    except urllib.error.HTTPError as error:
        return f"GitHub refused a token for {repo} ({error.code}). Is the app installed on it?"
    url = f"https://x-access-token:{repo_token}@github.com/{app['owner']}/{repo}.git"
    result = subprocess.run(["git", "--git-dir", str(git_dir), "push", "--porcelain", url, "main"],
                            capture_output=True, text=True)
    if result.returncode == 0:
        return "already backed up" if "[up to date]" in result.stdout else f"pushed to {repo}"
    if "rejected" in result.stdout + result.stderr:
        return f"not pushed: {repo} has commits we don't (was history rewritten?)"
    return "not pushed: " + (result.stderr.strip().replace(repo_token, "***") or "push failed")


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
# The button that starts it: a form that posts the manifest to GitHub.
APP_FORM = f"""<form method="post" action="https://github.com/settings/apps/new?state={STATE}" target="_blank">
<input type="hidden" name="manifest" value="{html.escape(json.dumps(MANIFEST))}">
<button>Create GitHub App</button></form>"""
NEW_REPO = "https://github.com/new?name={}&visibility=private"  # GitHub's form, filled in
SETUP_PAGE = f"""<!doctype html><title>Connect GitHub</title>
<body style="font: 16px system-ui; max-width: 36em; margin: 4em auto">
<h1>Connect your agent to GitHub</h1>
<p>1. Create two empty private repos (don't add a README):
<a href="{NEW_REPO.format('agent-workspace')}" target="_blank">agent-workspace</a> for the agent's
files, and <a href="{NEW_REPO.format('agent-history')}" target="_blank">agent-history</a> for your
conversations (any name ending in <code>-history</code> or <code>-chats</code>).</p>
<p>2. Create a private GitHub App for your agent. GitHub then asks which repos
it may use: pick <b>Only select repositories</b> and those two.</p>{APP_FORM}"""


class Setup(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path == "/github":
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
            workspace, history = pick_repos(app)
            app["backup_repo"] = workspace
            save_app(app)
            print(f"github: installed. Workspace -> {workspace}, chat log -> {history}. Done.")
            self.reply(200, f"<h1>Done.</h1><p>Workspace backs up to <b>{workspace or '(none picked)'}</b>, "
                            f"conversations to <b>{history or '(no repo ending in -history or -chats)'}</b>. "
                            "You can close this tab.</p>")
            if not getattr(self.server, "wizard", False):  # ./setup --web keeps running until Finish
                threading.Thread(target=self.server.shutdown).start()
        else:
            self.reply(400, "Unexpected request. Start again from the first page.")

    def reply(self, status, page):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode())


def serve():
    """Run the setup page until the app is installed."""
    host = os.environ.get("SETUP_HOST", "127.0.0.1")  # 0.0.0.0 inside Docker
    http.server.HTTPServer((host, PORT), Setup).serve_forever()


if __name__ == "__main__":
    print(f"github: open {SETUP_URL}/github in your browser")
    serve()

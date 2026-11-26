"""Set up your agent: a few questions, checked as you go, then .env is written.

    ./setup            the questions, here in the terminal
    ./setup --web      the same, as a page (./setup prints the link)

`./setup` runs this inside Docker (so you need nothing else installed), then
starts everything. Run it again any time to change something: what's already
set is kept unless you replace it.
"""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from harness import github

PROJECT = Path("/project")       # the folder with compose.yaml, mounted in by ./setup
ENV = PROJECT / ".env"
TAILSCALE_DNS = "https://login.tailscale.com/admin/dns"
TAILSCALE_KEYS = "https://login.tailscale.com/admin/settings/keys"
BROWSER_PORT = os.environ.get("SETUP_PORT", "8090")  # ./setup picks a free one
TUNNEL_HINT = f"(On a server: log in with  ssh -L {BROWSER_PORT}:localhost:{BROWSER_PORT} ...  so that link works.)"


# --- .env --------------------------------------------------------------------

def read_env():
    values = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def write_env(updates):
    """Change some lines of .env, keep the rest."""
    values = {**read_env(), **{k: v for k, v in updates.items() if v}}
    ENV.write_text("# Written by ./setup. Run it again to change anything.\n"
                   + "".join(f"{key}={value}\n" for key, value in values.items()))
    ENV.chmod(0o600)  # tokens: only you can read it


# --- the checks ----------------------------------------------------------------

def check_claude(token):
    """Does this login token work? One tiny call to find out."""
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "haiku", "--tools", "", "--no-session-persistence",
             "Reply with just the word OK."],
            env={"PATH": os.environ["PATH"], "HOME": tempfile.mkdtemp(), "CLAUDE_CODE_OAUTH_TOKEN": token},
            capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0 and "ok" in result.stdout.lower()


def telegram(token, method, **params):
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}",
                                     data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)["result"]


def check_telegram(token):
    """The bot's @name if the token works, else None."""
    try:
        return "@" + telegram(token, "getMe")["username"]
    except Exception:
        return None


def find_chat(token, seconds=180):
    """Wait for the person to message their bot, and return their chat id."""
    offset, deadline = 0, time.time() + seconds
    while time.time() < deadline:
        for update in telegram(token, "getUpdates", offset=offset, timeout=20):
            offset = update["update_id"] + 1
            chat = (update.get("message") or {}).get("chat", {})
            if chat.get("type") == "private":
                telegram(token, "getUpdates", offset=offset, timeout=0)  # mark it read
                telegram(token, "sendMessage", chat_id=chat["id"],
                         text="✅ Found you. Your agent will talk to you here.")
                return chat["id"]
    return None


def check_timezone(name):
    return (Path("/usr/share/zoneinfo") / name).is_file()


def check_tailscale(key):
    return key.startswith("tskey-auth-")


def prepare_folders():
    """On a server everything belongs to root, but the agent's services run as
    an ordinary user (uid 1000): give it its own folders."""
    for name in ["agent", "agent/sites", "agent/uploads"]:
        folder = PROJECT / name
        folder.mkdir(exist_ok=True)
        if folder.stat().st_uid == 0:
            subprocess.run(["chown", "-R", "1000:1000", str(folder)])


# --- the terminal version -----------------------------------------------------

def ask(question, default=""):
    answer = input(f"{question}{f' [{default}]' if default else ''}: ").strip()
    return answer or default


def keep(name, current):
    """Already set? Then ask whether to keep it."""
    if not current:
        return False
    return ask(f"{name} is already set. Keep it? (Y/n)", "y").lower().startswith("y")


def step(number, title):
    print(f"\n── {number}/5  {title} " + "─" * (50 - len(title)))


def cli():
    env, new = read_env(), {}
    print("Let's set up your agent. Five steps, about 15 minutes.")

    step(1, "Claude login")
    if not keep("Your Claude login", env.get("CLAUDE_CODE_OAUTH_TOKEN")):
        print("Next, Claude shows a link. Open it, log in with your Claude account (Pro or Max),\n"
              "and paste the code back here. Claude then prints a token starting with sk-ant-oat.\n")
        subprocess.run(["claude", "setup-token"], env={"PATH": os.environ["PATH"], "HOME": tempfile.mkdtemp()})
        while True:
            token = ask("\nPaste the token it printed")
            print("Checking it...")
            if check_claude(token):
                print("✓ Claude login works.")
                new["CLAUDE_CODE_OAUTH_TOKEN"] = token
                break
            print("✗ That token doesn't work. Copy the whole line starting with sk-ant-oat and try again.")

    step(2, "Telegram")
    if not keep("Your Telegram bot", env.get("TELEGRAM_BOT_TOKEN")):
        print("On Telegram, open @BotFather, send /newbot, and pick a name and a username.\n"
              "It replies with a token like 123456:ABC-...")
        while True:
            token = ask("Paste the bot token")
            bot = check_telegram(token)
            if bot:
                print(f"✓ Your bot is {bot}.")
                new["TELEGRAM_BOT_TOKEN"] = token
                break
            print("✗ Telegram doesn't know that token. Copy it again from BotFather.")
        print(f"\nNow open {bot} on Telegram and send it any message (\"hi\")...")
        chat = find_chat(token)
        if chat:
            print("✓ Found you: only you can talk to your agent.")
            new["TELEGRAM_CHAT_ID"] = str(chat)
        else:
            print("✗ No message came. Run ./setup again when you're ready.")
            return False

    step(3, "Your timezone")
    zone = ask("Your timezone, for reminders like \"at 6pm\"", env.get("TZ") or os.environ.get("HOST_TZ", "UTC"))
    while not check_timezone(zone):
        zone = ask("✗ Unknown timezone. Use a name like America/New_York or Asia/Tokyo")
    new["TZ"] = zone

    step(4, "Private access (Tailscale)")
    if not keep("Your Tailscale key", env.get("TS_AUTHKEY")):
        print("Your agent's pages are only reachable from your own devices, through Tailscale.\n"
              "1. Sign up at https://tailscale.com and install Tailscale on your phone and laptop.\n"
              f"2. On {TAILSCALE_DNS}, turn on MagicDNS and HTTPS Certificates.\n"
              f"3. On {TAILSCALE_KEYS}, click \"Generate auth key\" (the defaults are fine).\n"
              "   Tailscale shows the key only once: copy the whole thing before closing that window.")
        key = ask("Paste the key (tskey-auth-...)")
        while not check_tailscale(key):
            key = ask("✗ That's not a whole auth key. It starts with tskey-auth-. Copy all of it,\n"
                      "  or generate a new one if that window is closed")
        new["TS_AUTHKEY"] = key

    step(5, "GitHub backups")
    if github.load_app() and ask("GitHub is already connected. Keep it? (Y/n)", "y").lower().startswith("y"):
        pass
    elif ask("Back up your agent to GitHub? You can do it later. (Y/n)", "y").lower().startswith("y"):
        print(f"Open {github.SETUP_URL}/github in your browser and follow the page.\n" + TUNNEL_HINT)
        github.serve()  # returns once the app is installed
        print("✓ GitHub connected.")

    write_env(new)
    prepare_folders()
    print("\n✓ Saved. Starting your agent...")
    return True


# --- the web version ----------------------------------------------------------
# The same steps as a page. Each check is a small JSON call; "Finish" writes .env.

PAGE = (Path(__file__).parent / "wizard.html").read_text()


class Wizard(github.Setup):  # the GitHub app pages (/github, /created, /installed) come with it
    def do_GET(self):
        if self.path == "/":
            env = read_env()
            state = {"claude": bool(env.get("CLAUDE_CODE_OAUTH_TOKEN")),
                     "telegram": bool(env.get("TELEGRAM_CHAT_ID")),
                     "tz": env.get("TZ") or os.environ.get("HOST_TZ", ""),
                     "tailscale": bool(env.get("TS_AUTHKEY")),
                     "github": bool(github.load_app())}
            page = PAGE.replace("/*STATE*/{}", json.dumps(state)).replace("<!--APP_FORM-->", github.APP_FORM)
            return self.reply(200, page)
        if self.path == "/github/status":  # the page asks when you come back from GitHub's tab
            return self.reply(200, json.dumps({"ok": bool(github.load_app())}))
        super().do_GET()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        value = body.get("value", "").strip()
        if self.path == "/check/claude":
            ok = check_claude(value)
            self.pending["CLAUDE_CODE_OAUTH_TOKEN"] = value if ok else None
            answer = {"ok": ok}
        elif self.path == "/check/telegram":
            bot = check_telegram(value)
            self.pending["TELEGRAM_BOT_TOKEN"] = value if bot else None
            answer = {"ok": bool(bot), "bot": bot}
        elif self.path == "/check/chat":
            token = self.pending.get("TELEGRAM_BOT_TOKEN") or read_env().get("TELEGRAM_BOT_TOKEN")
            chat = find_chat(token, seconds=60)
            self.pending["TELEGRAM_CHAT_ID"] = str(chat) if chat else None
            answer = {"ok": bool(chat)}
        elif self.path == "/check/tz":
            ok = check_timezone(value)
            self.pending["TZ"] = value if ok else None
            answer = {"ok": ok}
        elif self.path == "/check/tailscale":
            ok = check_tailscale(value)
            self.pending["TS_AUTHKEY"] = value if ok else None
            answer = {"ok": ok}
        elif self.path == "/finish":
            write_env(self.pending)
            prepare_folders()
            answer = {"ok": True}
        else:
            return self.send_error(404)
        data = json.dumps(answer).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)
        if self.path == "/finish":  # saved: stop the page so ./setup can start the agent
            threading.Thread(target=self.server.shutdown).start()

    pending = {}  # checked values, written to .env on Finish

    def log_message(self, *args):
        pass  # keep the terminal quiet


def web():
    server = http.server.ThreadingHTTPServer((os.environ.get("SETUP_HOST", "127.0.0.1"), github.PORT), Wizard)
    server.wizard = True
    print(f"Open {github.SETUP_URL} in your browser.\n" + TUNNEL_HINT)
    server.serve_forever()  # until Finish
    print("✓ Saved. Starting your agent...")
    return True


if __name__ == "__main__":
    if sys.argv[1:2] == ["--urls"]:  # ./setup, once Tailscale is up: the agent's addresses
        write_env({"SITES_URL": sys.argv[2], "SECRETS_URL": sys.argv[2] + ":8443"})
    else:
        sys.exit(0 if (web() if "--web" in sys.argv else cli()) else 1)

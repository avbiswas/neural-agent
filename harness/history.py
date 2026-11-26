"""The conversation log: every message you send and the agent's reply, one
markdown file a day in history/. The harness writes it and backs it up to its
own GitHub repo (<you>/agent-history) every hour. The agent can read it (it
greps it to recall older conversations) but never change it.

Only the messages, never tool calls. Any saved secret is masked first.
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path

from harness import github

HISTORY = Path(__file__).parents[1] / "agent" / "history"
SECRETS = Path(os.environ.get("SECRETS_DIR", "/run/agent-secrets"))


def mask(text):
    """Replace the value of every saved secret with ***."""
    if SECRETS.is_dir():
        for path in SECRETS.iterdir():
            value = path.read_text().strip()
            if len(value) >= 6:
                text = text.replace(value, "***")
    return text


def log(where, message, reply):
    """Append one exchange. where: 'telegram', 'cli', 'site chat: <site> · opus'..."""
    now = datetime.now()
    HISTORY.mkdir(parents=True, exist_ok=True)
    entry = f"\n## {now:%H:%M} · {where}\n\n**You:** {message}\n\n**Agent:** {reply}\n"
    with open(HISTORY / f"{now:%Y-%m-%d}.md", "a") as file:
        file.write(mask(entry))


def backup():
    """Commit the log and push it to the -history repo. Says how it went."""
    git = lambda *args: subprocess.run(["git", "-C", str(HISTORY), *args], capture_output=True, text=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    if not (HISTORY / ".git").exists():
        git("init", "-q", "-b", "main")
        git("config", "user.name", "harness")
        git("config", "user.email", "harness@localhost")
    git("add", "-A")
    if git("diff", "--cached", "--quiet").returncode:  # something new
        git("commit", "-q", "-m", f"Conversations up to {datetime.now():%Y-%m-%d %H:%M}")
    if git("rev-parse", "HEAD").returncode:
        return "nothing to back up yet"
    app = github.load_app()
    if not app:
        return "not backed up (GitHub isn't connected: see github.py)"
    _, repo = github.pick_repos(app)
    if not repo:
        return "not backed up (no repo ending in -history or -chats: see ONBOARDING.md)"
    return github.push(app, HISTORY / ".git", repo)

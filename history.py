"""The conversation log: every message you send and the agent's reply, one
markdown file a day in agent/history/. It's part of the workspace, so the
hourly commit backs it up to GitHub, and the agent can grep it to recall
older conversations ("what did we decide last week?").

Only the messages, never tool calls. Any saved secret is masked first.
"""
import os
from datetime import datetime
from pathlib import Path

HISTORY = Path(__file__).parent / "agent" / "history"
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

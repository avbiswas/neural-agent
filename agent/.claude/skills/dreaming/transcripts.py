"""Read your past conversations (Claude Code's session files) without the noise.

    python3 .claude/skills/dreaming/transcripts.py messages SINCE    # what the person said since SINCE
    python3 .claude/skills/dreaming/transcripts.py context REF [N]   # N messages either side of one

SINCE is a UTC time like 2026-11-26T08:00:00Z. REF is what `messages` prints
in front of each message (session:line). Only conversation text is shown:
tool calls and tool results are left out on purpose.
"""
import json
import sys
from pathlib import Path

SESSIONS = Path.home() / ".claude" / "projects"  # HOME is the agent's own home
# Sessions that start with one of these were started by the harness, not the person.
NOT_THE_PERSON = ("A follow-up you scheduled", "A schedule you set", "Time to dream", "Time to commit", "[Site chat]")


def conversation(path):
    """[(line, who, timestamp, text)] for one session file: the person's
    messages and the agent's text replies, nothing else."""
    turns = []
    for line, raw in enumerate(path.read_text().splitlines()):
        entry = json.loads(raw)
        content = entry.get("message", {}).get("content")
        if entry.get("type") == "user" and isinstance(content, str):
            turns.append((line, "person", entry["timestamp"], content))
        elif entry.get("type") == "assistant":
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            if text:
                turns.append((line, "agent", entry["timestamp"], text))
    return turns


def show(ref, who, timestamp, text, limit=None):
    text = text if limit is None or len(text) <= limit else text[:limit] + " …"
    print(f"[{ref}] {timestamp[:16].replace('T', ' ')} {who}: " + text.replace("\n", "\n    "))


command, args = sys.argv[1], sys.argv[2:]
if command == "messages":
    since = args[0]
    for path in sorted(SESSIONS.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime):
        turns = conversation(path)
        if not turns or turns[0][3].startswith(NOT_THE_PERSON):
            continue
        for line, who, timestamp, text in turns:
            if who == "person" and timestamp > since:
                show(f"{path.stem[:8]}:{line}", who, timestamp, text)
elif command == "context":
    session, line = args[0].split(":")
    around = int(args[1]) if len(args) > 1 else 3
    path = next(SESSIONS.glob(f"*/{session}*.jsonl"))
    turns = conversation(path)
    at = next(i for i, turn in enumerate(turns) if turn[0] == int(line))
    for turn in turns[max(0, at - around):at + around + 1]:
        show(f"{session}:{turn[0]}", *turn[1:], limit=600)
else:
    print(__doc__)

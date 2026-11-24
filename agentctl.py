"""Poke the agent from the terminal.

    uv run agentctl.py say "hello"     # put an event in the inbox
    uv run agentctl.py inbox           # show recent events
"""
import sys

from db import connect

db = connect()
command, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("help", [])

if command == "say":
    db.execute("INSERT INTO events (source, text) VALUES ('cli', ?)", (" ".join(args),))
    print("queued")
elif command == "inbox":
    for e in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 10"):
        reply = (e["reply"] or "").replace("\n", " ")[:60]
        print(f"#{e['id']:<3} {e['status']:<10} {e['text'][:40]!r:<44} {reply}")
else:
    print(__doc__)

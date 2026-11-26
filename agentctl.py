"""Poke the agent from the terminal.

    uv run agentctl.py say "hello"     # put an event in the inbox
    uv run agentctl.py inbox           # show recent events
    uv run agentctl.py timers          # show recent timers
    uv run agentctl.py watch           # live view: timers -> events -> outbox
"""
import sys
import time

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
elif command == "timers":
    for t in db.execute("SELECT * FROM timers ORDER BY id DESC LIMIT 10"):
        print(f"#{t['id']:<3} {t['status']:<10} due {t['due_at']} UTC  {t['cron'] or '':<12} {t['prompt'][:50]!r}")
elif command == "watch":
    # The whole pipeline on one screen, refreshed twice a second.
    views = {  # name: (query, column widths)
        "timers": ("SELECT id, status, time(due_at, 'localtime'), cron, prompt FROM timers", (4, 10, 9, 14, 50)),
        "events": ("SELECT id, source, status, text, reply FROM events", (4, 9, 11, 40, 40)),
        "outbox": ("SELECT id, channel, status, text FROM outbox", (4, 9, 8, 50)),
    }
    while True:
        screen = []
        for name, (query, widths) in views.items():
            screen.append(f"── {name}")
            for row in db.execute(f"{query} ORDER BY id DESC LIMIT 4"):
                cells = [str(v or "").replace("\n", " ")[:w - 1].ljust(w) for v, w in zip(row, widths)]
                screen.append("  " + "".join(cells))
            screen.append("")
        print("\033[H\033[2J" + "\n".join(screen), flush=True)  # clear, then redraw
        time.sleep(0.5)
else:
    print(__doc__)

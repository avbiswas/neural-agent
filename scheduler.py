"""Turns due timers into inbox events. The agent is never called from here:
a timer is just one more thing that writes a row into `events`.

    uv run scheduler.py
"""
import time

from db import connect

db = connect()
print("scheduler: running")

while True:
    db.execute("BEGIN")  # fire + enqueue together: a crash can't lose or double a timer
    due = db.execute("""
        UPDATE timers SET status = 'fired'
        WHERE status = 'pending' AND due_at <= datetime('now')
        RETURNING *
    """).fetchall()
    for timer in due:
        db.execute("INSERT INTO events (source, text) VALUES ('timer', ?)",
                   (f"A follow-up you scheduled has fired (timer #{timer['id']}): {timer['prompt']}",))
        print(f"scheduler: timer #{timer['id']} fired -> inbox   {timer['prompt']!r}")
    db.execute("COMMIT")
    time.sleep(1)

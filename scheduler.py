"""Turns due timers into inbox events. The agent is never called from here:
a timer is just one more thing that writes a row into `events`.

    uv run scheduler.py
"""
import time

from db import connect, next_run

db = connect()
print("scheduler: running")

while True:
    db.execute("BEGIN")  # fire + enqueue together: a crash can't lose or double a timer
    for timer in db.execute("""
        SELECT * FROM timers WHERE status = 'pending' AND due_at <= datetime('now')
    """).fetchall():
        if timer["cron"]:
            # A schedule stays pending and moves to its next run, counted from now.
            # So if the Mac slept through 8 runs, it fires once now, not 8 times.
            db.execute("UPDATE timers SET due_at = ? WHERE id = ?", (next_run(timer["cron"]), timer["id"]))
            text = f"A schedule you set has fired (timer #{timer['id']}, {timer['cron']}): {timer['prompt']}"
        else:
            db.execute("UPDATE timers SET status = 'fired' WHERE id = ?", (timer["id"],))
            text = f"A follow-up you scheduled has fired (timer #{timer['id']}): {timer['prompt']}"
        db.execute("INSERT INTO events (source, text) VALUES ('timer', ?)", (text,))
        print(f"scheduler: timer #{timer['id']} fired -> inbox   {timer['prompt']!r}")
    db.execute("COMMIT")
    time.sleep(1)

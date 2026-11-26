"""Turns due timers into inbox events. The agent is never called from here:
a timer is just one more thing that writes a row into `events`.

    uv run scheduler.py
"""
import time

from db import connect, next_run

db = connect()

# The nightly dream (see dream.py) is a schedule like any other, owned by the harness.
NIGHTLY_DREAM = "0 3 * * *"
if not db.execute("SELECT 1 FROM timers WHERE prompt = '/dream' AND status = 'pending'").fetchone():
    db.execute("INSERT INTO timers (prompt, due_at, cron) VALUES ('/dream', ?, ?)",
               (next_run(NIGHTLY_DREAM), NIGHTLY_DREAM))
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
            what = f"A schedule you set has fired (timer #{timer['id']}, {timer['cron']})"
        else:
            db.execute("UPDATE timers SET status = 'fired' WHERE id = ?", (timer["id"],))
            what = f"A follow-up you scheduled has fired (timer #{timer['id']})"
        # A harness command like /dream goes in as is: the worker handles it, not the agent.
        text = timer["prompt"] if timer["prompt"].startswith("/") else f"{what}: {timer['prompt']}"
        db.execute("INSERT INTO events (source, text) VALUES ('timer', ?)", (text,))
        print(f"scheduler: timer #{timer['id']} fired -> inbox   {timer['prompt']!r}")
    db.execute("COMMIT")
    time.sleep(1)

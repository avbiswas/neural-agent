"""Turns due timers into inbox events. The agent is never called from here:
a timer is just one more thing that writes a row into `events`.

    uv run python -m harness.scheduler
"""
import time

from harness.db import connect, next_run

db = connect()

# The harness's own schedules: the nightly dream (see dream.py) and the hourly
# commit (see commit.py). Schedules like any other, just not set by the agent.
for command, cron in [("/dream", "0 3 * * *"), ("/commit", "0 * * * *")]:
    if not db.execute("SELECT 1 FROM timers WHERE prompt = ? AND status = 'pending'", (command,)).fetchone():
        db.execute("INSERT INTO timers (prompt, due_at, cron) VALUES (?, ?, ?)",
                   (command, next_run(cron), cron))
print("scheduler: running")

while True:
    db.execute("BEGIN")  # fire + enqueue together: a crash can't lose or double a timer
    for timer in db.execute("""
        SELECT * FROM timers WHERE status = 'pending' AND due_at <= datetime('now')
    """).fetchall():
        if timer["cron"]:
            # A schedule stays pending and moves to its next run, counted from now.
            # So if the computer slept through 8 runs, it fires once now, not 8 times.
            db.execute("UPDATE timers SET due_at = ? WHERE id = ?", (next_run(timer["cron"]), timer["id"]))
            what = f"A schedule you set has fired (timer #{timer['id']}, {timer['cron']})"
        else:
            db.execute("UPDATE timers SET status = 'fired' WHERE id = ?", (timer["id"],))
            what = f"A follow-up you scheduled has fired (timer #{timer['id']})"
        # A harness command like /dream goes in as is: the worker handles it, not the agent.
        text = timer["prompt"] if timer["prompt"].startswith("/") else f"{what}: {timer['prompt']}"
        db.execute("INSERT INTO events (source, text, model) VALUES ('timer', ?, ?)", (text, timer["model"]))
        print(f"scheduler: timer #{timer['id']} fired -> inbox   {timer['prompt']!r}")
    db.execute("COMMIT")
    time.sleep(1)

"""The console channel: delivers the agent's replies to this terminal.

    uv run console.py
"""
import time

from db import connect

db = connect()
print("console: waiting for replies...")

while True:
    # Deliver every pending message for this channel, oldest first.
    for message in db.execute("""
        SELECT * FROM outbox WHERE channel = 'cli' AND status = 'pending' ORDER BY id
    """).fetchall():
        print(f"\nagent> {message['text']}")
        db.execute("UPDATE outbox SET status = 'sent' WHERE id = ?", (message["id"],))
    time.sleep(0.5)

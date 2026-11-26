"""The console channel: delivers the agent's replies to this terminal.

    uv run python -m channels.console
"""
import time

from harness.db import connect

db = connect()
print("console: waiting for replies...")

while True:
    # Deliver every pending message for this channel, oldest first.
    for message in db.execute("""
        SELECT * FROM outbox WHERE channel = 'cli' AND status = 'pending' ORDER BY id
    """).fetchall():
        print(f"\nagent> {message['text']}")
        db.execute("UPDATE outbox SET status = 'sent' WHERE id = ?", (message["id"],))
    # Approval requests: answer them with agentctl.
    for approval in db.execute("SELECT * FROM approvals WHERE channel = 'cli' AND NOT shown").fetchall():
        print(f"\nagent> May I {approval['request']}\n"
              f"       uv run python -m harness.agentctl approve {approval['id']}   (or deny {approval['id']})")
        db.execute("UPDATE approvals SET shown = 1 WHERE id = ?", (approval["id"],))
    time.sleep(0.5)

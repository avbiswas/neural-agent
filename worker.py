import time

from db import connect

db = connect()
print("worker: waiting for events...")

while True:
    # Claim the oldest pending event (pending -> processing) in one statement.
    event = db.execute("""
        UPDATE events SET status = 'processing'
        WHERE id = (SELECT id FROM events WHERE status = 'pending' ORDER BY id LIMIT 1)
        RETURNING *
    """).fetchone()

    if event is None:
        time.sleep(1)
        continue

    print(f"worker: #{event['id']} pending -> processing   {event['text']!r}")

    time.sleep(3)  # pretend to work: the agent goes here in the next stage
    reply = f"echo: {event['text']}"

    db.execute("UPDATE events SET status = 'done', reply = ? WHERE id = ?",
               (reply, event["id"]))
    print(f"worker: #{event['id']} processing -> done      reply={reply!r}")

import time

from db import connect
from agent import run_agent

db = connect()

# Crash recovery: anything a dead worker left 'processing' goes back in the queue.
recovered = db.execute("UPDATE events SET status = 'pending' WHERE status = 'processing'").rowcount
if recovered:
    print(f"worker: recovered {recovered} event(s) left processing by a previous run")

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

    # Every event continues one 'chat' conversation (for now).
    row = db.execute("SELECT session_id FROM sessions WHERE key = 'chat'").fetchone()
    try:
        result = run_agent(event["text"], row["session_id"] if row else None)
    except Exception as error:
        db.execute("UPDATE events SET status = 'failed', reply = ? WHERE id = ?",
                   (str(error), event["id"]))
        print(f"worker: #{event['id']} processing -> failed    {error}")
        continue
    reply = result["text"]

    db.execute("""
        INSERT INTO sessions (key, session_id) VALUES ('chat', ?)
        ON CONFLICT (key) DO UPDATE SET session_id = excluded.session_id,
                                        updated_at = CURRENT_TIMESTAMP
    """, (result["session_id"],))
    db.execute("UPDATE events SET status = 'done', reply = ? WHERE id = ?",
               (reply, event["id"]))
    print(f"worker: #{event['id']} processing -> done      reply={reply!r}")
    print(f"        tokens in={result['input_tokens']} out={result['output_tokens']} "
          f"cost=${result['cost_usd']:.4f}")

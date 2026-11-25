import time

from db import connect
from agent import run_agent

db = connect()

# Sources that are a person chatting. Their pending messages get batched;
# everything else (timers, later) runs one event at a time.
USER_SOURCES = ("cli", "telegram")

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

    # Batching: if it's a user message, also claim every other pending user
    # message, so "hi" / "one more thing" / "actually..." become one run.
    events = [event]
    marks = ",".join("?" * len(USER_SOURCES))
    if event["source"] in USER_SOURCES:
        events += db.execute(f"""
            UPDATE events SET status = 'processing'
            WHERE status = 'pending' AND source IN ({marks})
            RETURNING *
        """, USER_SOURCES).fetchall()
    events.sort(key=lambda e: e["id"])
    ids = " ".join(f"#{e['id']}" for e in events)

    if len(events) == 1:
        prompt = event["text"]
    else:
        prompt = "The user sent several messages. Answer them together:\n" + "\n".join(
            f"- {e['text']}" for e in events)
    print(f"worker: {ids} pending -> processing   {prompt!r}")

    # Steering: user messages that arrive while the agent is running get
    # claimed and pushed straight into the running turn.
    def more_messages():
        if events[0]["source"] not in USER_SOURCES:
            return []
        new = db.execute(f"""
            UPDATE events SET status = 'processing'
            WHERE status = 'pending' AND source IN ({marks})
            RETURNING *
        """, USER_SOURCES).fetchall()
        for e in new:
            print(f"worker: #{e['id']} pending -> processing   {e['text']!r}  (steered into the running turn)")
        events.extend(new)
        return [e["text"] for e in new]

    # Every event continues one 'chat' conversation (for now).
    row = db.execute("SELECT session_id FROM sessions WHERE key = 'chat'").fetchone()
    try:
        result = run_agent(prompt, row["session_id"] if row else None, more_messages)
    except Exception as error:
        db.executemany("UPDATE events SET status = 'failed', reply = ? WHERE id = ?",
                       [(str(error), e["id"]) for e in events])
        print(f"worker: {' '.join(f'#{e[0]}' for e in events)} processing -> failed    {error}")
        continue
    reply = result["text"]
    ids = " ".join(f"#{e['id']}" for e in events)

    db.execute("""
        INSERT INTO sessions (key, session_id) VALUES ('chat', ?)
        ON CONFLICT (key) DO UPDATE SET session_id = excluded.session_id,
                                        updated_at = CURRENT_TIMESTAMP
    """, (result["session_id"],))
    db.executemany("UPDATE events SET status = 'done', reply = ? WHERE id = ?",
                   [(reply, e["id"]) for e in events])
    # The outbox: the reply goes back to the channel the message came from.
    # The worker only writes it; a channel process (console.py) delivers it.
    if events[0]["source"] in USER_SOURCES:
        db.execute("INSERT INTO outbox (channel, text) VALUES (?, ?)",
                   (events[0]["source"], reply))
    print(f"worker: {ids} processing -> done      reply={reply!r}")
    print(f"        tokens in={result['input_tokens']} out={result['output_tokens']} "
          f"cost=${result['cost_usd']:.4f}")

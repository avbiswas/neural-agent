import time

from db import connect
from agent import run_agent

db = connect()

# Sources that are a person chatting. Their pending messages get batched;
# everything else (timers, later) runs one event at a time.
USER_SOURCES = ("cli", "telegram")
marks = ",".join("?" * len(USER_SOURCES))

# Session policy for the chat: resume if the last run was recent, else start fresh.
IDLE_LIMIT_MINUTES = 60   # the prompt cache lives ~1h, so resuming within it is cheap

# User messages that may join the current run (batching or steering): pending,
# from a person, and not past a pending /new, which must split the conversation.
JOINABLE = f"""status = 'pending' AND source IN ({marks}) AND trim(text) != '/new'
    AND id < (SELECT coalesce(min(id), 1e18) FROM events
              WHERE status = 'pending' AND trim(text) = '/new')"""


def pick_session():
    """Return (session_id or None, reason) for the next chat run."""
    row = db.execute("""
        SELECT session_id,
               (julianday('now') - julianday(updated_at)) * 24 * 60 AS idle_minutes
        FROM sessions WHERE key = 'chat'
    """).fetchone()
    if row is None:
        return None, "new (no conversation yet)"
    idle = int(row["idle_minutes"])
    if idle < IDLE_LIMIT_MINUTES:
        return row["session_id"], f"resume ({idle} min since last run)"
    return None, f"new (idle {idle} min)"


def reply_to(events, text):
    """Mark events done and put the reply in the outbox, addressed to the channel
    the message came from. Channel processes (console.py, telegram.py) deliver it."""
    db.executemany("UPDATE events SET status = 'done', reply = ? WHERE id = ?",
                   [(text, e["id"]) for e in events])
    if events[0]["source"] in USER_SOURCES:
        db.execute("INSERT INTO outbox (channel, text) VALUES (?, ?)",
                   (events[0]["source"], text))

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

    # /new: forget the chat session. The next message starts a fresh one.
    if event["text"].strip() == "/new":
        db.execute("DELETE FROM sessions WHERE key = 'chat'")
        reply_to([event], "Started a new conversation.")
        print(f"worker: #{event['id']} /new -> chat session cleared")
        continue

    # Batching: if it's a user message, also claim every other pending user
    # message, so "hi" / "one more thing" / "actually..." become one run.
    events = [event]
    if event["source"] in USER_SOURCES:
        events += db.execute(f"UPDATE events SET status = 'processing' WHERE {JOINABLE} RETURNING *",
                             USER_SOURCES).fetchall()
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
        new = db.execute(f"UPDATE events SET status = 'processing' WHERE {JOINABLE} RETURNING *",
                         USER_SOURCES).fetchall()
        for e in new:
            print(f"worker: #{e['id']} pending -> processing   {e['text']!r}  (steered into the running turn)")
        events.extend(new)
        return [e["text"] for e in new]

    session_id, why = pick_session()
    print(f"        session: {why}")
    try:
        result = run_agent(prompt, session_id, more_messages, channel=events[0]["source"])
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
    reply_to(events, reply)  # -> outbox, delivered by console.py / telegram.py
    print(f"worker: {ids} processing -> done      reply={reply!r}")
    print(f"        tokens in={result['input_tokens']} out={result['output_tokens']} "
          f"context={result['context_tokens']} cost=${result['cost_usd']:.4f}")

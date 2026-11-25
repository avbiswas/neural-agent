"""The Telegram channel: the same job as console.py, over Telegram's Bot API.

    In:  long-poll getUpdates -> a row in `events` (source 'telegram')
    Out: pending 'telegram' rows in `outbox` -> sendMessage

    uv run telegram.py
"""
import json
import os
import threading
import time
import urllib.request

from agent import read_env_file
from db import DB_PATH, connect

config = {**read_env_file(".env", ".envrc"), **os.environ}
API = f"https://api.telegram.org/bot{config['TELEGRAM_BOT_TOKEN']}"
# Only this chat may talk to the agent. Anyone can find a bot, so this matters.
CHAT_ID = int(config["TELEGRAM_CHAT_ID"]) if config.get("TELEGRAM_CHAT_ID") else None
# Which updates we've already handled. Kept on disk: Telegram only forgets an
# update once a later getUpdates call completes, so a restart would replay it.
OFFSET_FILE = DB_PATH.parent / "telegram-offset"


def call(method, http_timeout=10, **params):
    """Call a Bot API method with JSON params and return its result.
    A short timeout: if a connection hangs, we fail fast and retry."""
    request = urllib.request.Request(f"{API}/{method}", data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=http_timeout) as response:
        return json.load(response)["result"]


def receive():
    """In: wait for new messages (long polling) and put them in the inbox."""
    db = connect()  # each thread gets its own SQLite connection
    offset = int(OFFSET_FILE.read_text()) if OFFSET_FILE.exists() else 0
    while True:
        try:
            # Long poll: Telegram holds the request up to 30s until a message arrives.
            updates = call("getUpdates", http_timeout=40, offset=offset, timeout=30)
        except Exception as error:
            print(f"telegram: receive failed ({error}), retrying")
            time.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            OFFSET_FILE.write_text(str(offset))  # "seen", even if we crash below
            message = update.get("message")
            if not message or "text" not in message:
                continue
            chat_id = message["chat"]["id"]
            if chat_id != CHAT_ID:
                print(f"telegram: ignored a message from chat {chat_id}. "
                      f"If that's you, add `export TELEGRAM_CHAT_ID={chat_id}` to .envrc")
                continue
            db.execute("INSERT INTO events (source, text) VALUES ('telegram', ?)", (message["text"],))
            print(f"telegram: in  {message['text']!r}")
            # 👀 = "got it". The reply comes later, through the outbox.
            call("setMessageReaction", chat_id=chat_id, message_id=message["message_id"],
                 reaction=[{"type": "emoji", "emoji": "👀"}])


def deliver():
    """Out: send pending outbox rows, and show 'typing…' while the agent works."""
    db = connect()
    last_typing = 0
    while True:
        for message in db.execute("""
            SELECT * FROM outbox WHERE channel = 'telegram' AND status = 'pending' ORDER BY id
        """).fetchall():
            try:
                text = message["text"]
                for start in range(0, len(text), 4000):  # Telegram's limit is 4096 chars
                    call("sendMessage", chat_id=CHAT_ID, text=text[start:start + 4000])
            except Exception as error:
                print(f"telegram: send failed ({error}), will retry")
                break  # it stays 'pending', so the next loop tries again
            db.execute("UPDATE outbox SET status = 'sent' WHERE id = ?", (message["id"],))
            print(f"telegram: out {message['text'][:60]!r}")

        busy = db.execute("""
            SELECT 1 FROM events WHERE source = 'telegram' AND status = 'processing'
        """).fetchone()
        if busy and time.time() - last_typing > 4:  # the indicator lasts ~5s
            try:
                call("sendChatAction", chat_id=CHAT_ID, action="typing")
            except Exception:
                pass
            last_typing = time.time()
        time.sleep(1)


if CHAT_ID is None:
    print("telegram: TELEGRAM_CHAT_ID not set. Message the bot and I'll print your chat id.")
threading.Thread(target=receive, daemon=True).start()
print("telegram: running")
deliver()

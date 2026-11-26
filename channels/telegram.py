"""The Telegram channel: the same job as channels/console.py, over Telegram's Bot API.

    In:  long-poll getUpdates -> a row in `events` (source 'telegram')
         Files (photos, documents, voice...) are saved in agent/uploads/, and
         the event tells the agent where
    Out: pending 'telegram' rows in `outbox` -> sendMessage
    Approvals: a message with Approve / Deny buttons; a press updates `approvals`

    uv run python -m channels.telegram
"""
import json
import os
import sys
import threading
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from harness.agent import WORKSPACE, read_env_file
from harness.db import DB_PATH, connect

config = {**read_env_file(".env", ".envrc"), **os.environ}
if not config.get("TELEGRAM_BOT_TOKEN"):
    sys.exit("telegram: no TELEGRAM_BOT_TOKEN. Get one from @BotFather and put it in .env")
API = f"https://api.telegram.org/bot{config['TELEGRAM_BOT_TOKEN']}"
# Only this chat may talk to the agent. Anyone can find a bot, so this matters.
CHAT_ID = int(config["TELEGRAM_CHAT_ID"]) if config.get("TELEGRAM_CHAT_ID") else None
# Which updates we've already handled. Kept on disk: Telegram only forgets an
# update once a later getUpdates call completes, so a restart would replay it.
OFFSET_FILE = DB_PATH.parent / "telegram-offset"
UPLOADS = WORKSPACE / "uploads"   # files you send, where the agent can read them
MAX_DOWNLOAD = 20 * 1024 * 1024   # the most a bot may download from Telegram


def call(method, http_timeout=10, **params):
    """Call a Bot API method with JSON params and return its result.
    A short timeout: if a connection hangs, we fail fast and retry."""
    request = urllib.request.Request(f"{API}/{method}", data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=http_timeout) as response:
        return json.load(response)["result"]


def save_file(message):
    """Download the file in a message, if there is one, into uploads/<date>/.
    Returns its path as the agent sees it (relative to its workspace), or an
    error to tell the person, or None for a plain text message."""
    kinds = ["document", "photo", "voice", "audio", "video", "video_note"]
    kind = next((k for k in kinds if k in message), None)
    if not kind:
        return None, None
    file = message[kind][-1] if kind == "photo" else message[kind]  # photos come in sizes: take the largest
    if file.get("file_size", 0) > MAX_DOWNLOAD:
        return None, "That file is over 20 MB, the most Telegram lets a bot download. Can you send a link instead?"
    remote = call("getFile", file_id=file["file_id"])["file_path"]
    name = file.get("file_name") or f"{kind}{Path(remote).suffix}"
    name = re.sub(r"[^\w.-]", "_", name)  # nothing that could act as a path
    path = UPLOADS / f"{datetime.now():%Y-%m-%d}" / f"{message['message_id']}-{name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://api.telegram.org/file/bot{config['TELEGRAM_BOT_TOKEN']}/{remote}"
    with urllib.request.urlopen(url, timeout=60) as response:
        path.write_bytes(response.read())
    return path.relative_to(WORKSPACE), None


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
            if "callback_query" in update:  # someone pressed Approve / Deny
                answer(db, update["callback_query"])
                continue
            message = update.get("message")
            if not message:
                continue
            chat_id = message["chat"]["id"]
            if chat_id != CHAT_ID:
                print(f"telegram: ignored a message from chat {chat_id}. "
                      f"If that's you, add `export TELEGRAM_CHAT_ID={chat_id}` to .envrc")
                continue
            text = message.get("text") or message.get("caption") or ""
            try:
                path, problem = save_file(message)
            except Exception as error:
                path, problem = None, f"I couldn't download that file ({error}). Try sending it again?"
            if problem:  # tell them right away, no need to wake the agent
                db.execute("INSERT INTO outbox (channel, text) VALUES ('telegram', ?)", (problem,))
                continue
            if path:
                text = f"[The person uploaded a file. It's saved at {path}]\n{text}".strip()
            if not text:
                continue  # a sticker, a location...: nothing we handle yet
            db.execute("INSERT INTO events (source, text) VALUES ('telegram', ?)", (text,))
            print(f"telegram: in  {text!r}")
            # 👀 = "got it". The reply comes later, through the outbox.
            call("setMessageReaction", chat_id=chat_id, message_id=message["message_id"],
                 reaction=[{"type": "emoji", "emoji": "👀"}])


def answer(db, press):
    """Record the person's decision, and replace the buttons with it."""
    if press["message"]["chat"]["id"] != CHAT_ID:
        return
    decision, approval_id = press["data"].split(":")
    decided = db.execute("UPDATE approvals SET status = ? WHERE id = ? AND status = 'pending'",
                         (decision, int(approval_id))).rowcount
    call("answerCallbackQuery", callback_query_id=press["id"],
         text=decision.capitalize() if decided else "Too late: this request has expired")
    if decided:
        label = "✅ Approved" if decision == "approved" else "❌ Denied"
        call("editMessageText", chat_id=CHAT_ID, message_id=press["message"]["message_id"],
             text=f"{press['message']['text']}\n\n{label}")
    print(f"telegram: approval #{approval_id} {decision if decided else 'expired'}")


def ask(db):
    """Show new approval requests, with buttons."""
    for approval in db.execute("""SELECT * FROM approvals
                                  WHERE channel = 'telegram' AND NOT shown ORDER BY id""").fetchall():
        try:
            call("sendMessage", chat_id=CHAT_ID, text=f"🔐 May I {approval['request']}",
                 reply_markup={"inline_keyboard": [[
                     {"text": "✅ Approve", "callback_data": f"approved:{approval['id']}"},
                     {"text": "❌ Deny", "callback_data": f"denied:{approval['id']}"}]]})
        except Exception as error:
            print(f"telegram: asking failed ({error}), will retry")
            return
        db.execute("UPDATE approvals SET shown = 1 WHERE id = ?", (approval["id"],))
        print(f"telegram: asked approval #{approval['id']}")


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
        ask(db)

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

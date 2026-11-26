"""The harness's MCP server: tools that let the agent act on the harness itself.
Claude Code starts it for each run (see --mcp-config in agent.py).

    send_message                            talk to the person mid-turn
    set_followup / list_timers / cancel_timer   wake yourself up later
"""
import os
from datetime import datetime, timedelta, timezone

from mcp.server.mcpserver import MCPServer

from db import connect

server = MCPServer("harness")
CHANNEL = os.environ["HARNESS_CHANNEL"]  # where this run's messages go, set by agent.py
DB_TIME = "%Y-%m-%d %H:%M:%S"            # how SQLite's CURRENT_TIMESTAMP writes UTC


def local(utc_text):
    """'2026-11-26 18:00:00' (UTC, from the db) -> 'Thu 26 Nov 19:00' in local time."""
    utc = datetime.strptime(utc_text, DB_TIME).replace(tzinfo=timezone.utc)
    return utc.astimezone().strftime("%a %d %b %H:%M")


@server.tool()
def send_message(text: str) -> str:
    """Send the person a chat message right now, in the middle of your turn.
    Your final message is delivered anyway, so don't use this to repeat it.
    Use it sparingly: e.g. a short heads-up before a task that will take a while."""
    connect().execute("INSERT INTO outbox (channel, text) VALUES (?, ?)", (CHANNEL, text))
    return "sent"


@server.tool()
def set_followup(prompt: str, in_minutes: float | None = None, at: str | None = None) -> str:
    """Wake yourself up later. When the timer fires, a new session of you
    starts with `prompt` as its task, and it remembers nothing of this
    conversation: write the prompt so it makes sense on its own (who, what,
    why, any links). Give either in_minutes, or at as a local time like
    '2026-11-26 18:00'."""
    if at:
        due = datetime.fromisoformat(at).astimezone(timezone.utc)  # naive = local time
    elif in_minutes is not None:
        due = datetime.now(timezone.utc) + timedelta(minutes=in_minutes)
    else:
        return "error: give in_minutes or at"
    if due < datetime.now(timezone.utc):
        return "error: that time has already passed"
    timer = connect().execute("INSERT INTO timers (prompt, due_at) VALUES (?, ?) RETURNING *",
                              (prompt, due.strftime(DB_TIME))).fetchone()
    return f"timer #{timer['id']} set for {local(timer['due_at'])}"


@server.tool()
def list_timers() -> str:
    """List your timers that haven't fired yet."""
    timers = connect().execute("SELECT * FROM timers WHERE status = 'pending' ORDER BY due_at")
    return "\n".join(f"#{t['id']} {local(t['due_at'])}: {t['prompt']}" for t in timers) or "no timers"


@server.tool()
def cancel_timer(timer_id: int) -> str:
    """Cancel a timer that hasn't fired yet."""
    cancelled = connect().execute("""UPDATE timers SET status = 'cancelled'
                                     WHERE id = ? AND status = 'pending'""", (timer_id,)).rowcount
    return f"timer #{timer_id} cancelled" if cancelled else f"no pending timer #{timer_id}"


if __name__ == "__main__":
    server.run()  # speaks MCP over stdin/stdout

"""The harness's MCP server: tools that let the agent act on the harness itself.
A service of its own: the agent reaches it over HTTP (see mcp_config in
agent.py), and only this side touches the database.

    send_message                            talk to the person mid-turn
    set_followup / create_schedule           wake yourself up later, once or repeatedly
    list_timers / cancel_timer               see and cancel both
"""
import os
from datetime import datetime, timedelta, timezone

from croniter import croniter
from mcp.server.mcpserver import MCPServer

from db import DB_TIME, connect, last_channel, next_run

server = MCPServer("harness")
MAX_SCHEDULES = 10                       # so a confused agent can't flood its own inbox


def local(utc_text):
    """'2026-11-26 18:00:00' (UTC, from the db) -> 'Thu 26 Nov 19:00' in local time."""
    utc = datetime.strptime(utc_text, DB_TIME).replace(tzinfo=timezone.utc)
    return utc.astimezone().strftime("%a %d %b %H:%M")


@server.tool()
def send_message(text: str) -> str:
    """Send the person a chat message right now, in the middle of your turn.
    Your final message is delivered anyway, so don't use this to repeat it.
    Use it sparingly: e.g. a short heads-up before a task that will take a while."""
    db = connect()
    db.execute("INSERT INTO outbox (channel, text) VALUES (?, ?)", (last_channel(db), text))
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
def create_schedule(cron: str, prompt: str) -> str:
    """Run `prompt` repeatedly, on a cron schedule in the person's local time,
    e.g. '0 8 * * *' for every day at 8:00, '0 9 * * 1' for Mondays at 9:00.
    Each run is a new session of you that remembers nothing else, so write the
    prompt to stand on its own. Runs are silent unless you use send_message."""
    if not croniter.is_valid(cron):
        return f"error: {cron!r} is not a valid cron expression"
    db = connect()
    count = db.execute("SELECT count(*) FROM timers WHERE cron IS NOT NULL AND status = 'pending'").fetchone()[0]
    if count >= MAX_SCHEDULES:
        return f"error: already {count} schedules. Cancel one first (list_timers)."
    timer = db.execute("INSERT INTO timers (prompt, due_at, cron) VALUES (?, ?, ?) RETURNING *",
                       (prompt, next_run(cron), cron)).fetchone()
    return f"schedule #{timer['id']} set ({cron}), first run {local(timer['due_at'])}"


@server.tool()
def list_timers() -> str:
    """List your pending follow-ups and schedules, with when each runs next."""
    timers = connect().execute("SELECT * FROM timers WHERE status = 'pending' ORDER BY due_at")
    return "\n".join(f"#{t['id']} next {local(t['due_at'])}" + (f" (repeats: {t['cron']})" if t["cron"] else "")
                     + f": {t['prompt']}" for t in timers) or "no timers"


@server.tool()
def cancel_timer(timer_id: int) -> str:
    """Cancel a follow-up that hasn't fired yet, or stop a schedule."""
    cancelled = connect().execute("""UPDATE timers SET status = 'cancelled'
                                     WHERE id = ? AND status = 'pending'""", (timer_id,)).rowcount
    return f"timer #{timer_id} cancelled" if cancelled else f"no pending timer #{timer_id}"


if __name__ == "__main__":
    # 0.0.0.0 in Docker, so the runner container can reach it (never published to the host).
    server.run("streamable-http", host=os.environ.get("MCP_HOST", "127.0.0.1"), port=8001)

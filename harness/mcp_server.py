"""The harness's MCP server: tools that let the agent act on the harness itself.
A service of its own: the agent reaches it over HTTP (see mcp_config in
agent.py), and only this side touches the database.

    send_message                            talk to the person mid-turn
    set_followup / create_schedule           wake yourself up later, once or repeatedly
    list_timers / cancel_timer               see and cancel both
    approve                                  Claude Code asks it before anything not allowed
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from croniter import croniter
from mcp.server.mcpserver import MCPServer

from harness.db import DB_TIME, connect, last_channel, next_run

server = MCPServer("harness")
MAX_SCHEDULES = 10                       # so a confused agent can't flood its own inbox
APPROVAL_TIMEOUT = 300                   # seconds to wait for the person before saying no


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
def set_followup(prompt: str, in_minutes: float | None = None, at: str | None = None,
                 model: str = "sonnet") -> str:
    """Wake yourself up later. When the timer fires, a new session of you
    starts with `prompt` as its task, and it remembers nothing of this
    conversation: write the prompt so it makes sense on its own (who, what,
    why, any links). Give either in_minutes, or at as a local time like
    '2026-11-26 18:00'. model: 'sonnet' (default: checks, reminders, monitoring)
    or 'opus' (research, writing, coding)."""
    if model not in ("sonnet", "opus"):
        return "error: model is 'sonnet' or 'opus'"
    if at:
        due = datetime.fromisoformat(at).astimezone(timezone.utc)  # naive = local time
    elif in_minutes is not None:
        due = datetime.now(timezone.utc) + timedelta(minutes=in_minutes)
    else:
        return "error: give in_minutes or at"
    if due < datetime.now(timezone.utc):
        return "error: that time has already passed"
    timer = connect().execute("INSERT INTO timers (prompt, due_at, model) VALUES (?, ?, ?) RETURNING *",
                              (prompt, due.strftime(DB_TIME), model)).fetchone()
    return f"timer #{timer['id']} set for {local(timer['due_at'])}"


@server.tool()
def create_schedule(cron: str, prompt: str, model: str = "sonnet") -> str:
    """Run `prompt` repeatedly, on a cron schedule in the person's local time,
    e.g. '0 8 * * *' for every day at 8:00, '0 9 * * 1' for Mondays at 9:00.
    Each run is a new session of you that remembers nothing else, so write the
    prompt to stand on its own. Runs are silent unless you use send_message.
    model: 'sonnet' (default: checks, digests, monitoring) or 'opus' (research,
    writing, coding)."""
    if model not in ("sonnet", "opus"):
        return "error: model is 'sonnet' or 'opus'"
    if not croniter.is_valid(cron):
        return f"error: {cron!r} is not a valid cron expression"
    db = connect()
    count = db.execute("SELECT count(*) FROM timers WHERE cron IS NOT NULL AND status = 'pending'").fetchone()[0]
    if count >= MAX_SCHEDULES:
        return f"error: already {count} schedules. Cancel one first (list_timers)."
    timer = db.execute("INSERT INTO timers (prompt, due_at, cron, model) VALUES (?, ?, ?, ?) RETURNING *",
                       (prompt, next_run(cron), cron, model)).fetchone()
    return f"schedule #{timer['id']} set ({cron}), first run {local(timer['due_at'])}"


@server.tool()
def list_timers() -> str:
    """List your pending follow-ups and schedules, with when each runs next."""
    timers = connect().execute("SELECT * FROM timers WHERE status = 'pending' ORDER BY due_at")
    return "\n".join(f"#{t['id']} next {local(t['due_at'])}" + (f" (repeats: {t['cron']})" if t["cron"] else "")
                     + f" [{t['model']}]: {t['prompt']}" for t in timers) or "no timers"


@server.tool()
def cancel_timer(timer_id: int) -> str:
    """Cancel a follow-up that hasn't fired yet, or stop a schedule."""
    cancelled = connect().execute("""UPDATE timers SET status = 'cancelled'
                                     WHERE id = ? AND status = 'pending'""", (timer_id,)).rowcount
    return f"timer #{timer_id} cancelled" if cancelled else f"no pending timer #{timer_id}"


def describe(tool_name, tool_input):
    """What the agent wants to do, in a form a person can judge quickly."""
    if tool_name == "Bash":
        why = f"\n\n({tool_input['description']})" if tool_input.get("description") else ""
        return f"run a command:\n\n{tool_input['command']}{why}"
    return f"use {tool_name}:\n\n{json.dumps(tool_input, indent=1)[:1500]}"


@server.tool()
async def approve(tool_name: str, input: dict, tool_use_id: str | None = None) -> dict:
    """The harness's permission check. Claude Code calls this itself whenever
    you try something that isn't allowed by default; don't call it yourself."""
    # Claude Code waits on this call (--permission-prompt-tool in agent.py).
    # We ask the person through their channel, and wait for their answer.
    db = connect()
    approval = db.execute("INSERT INTO approvals (channel, request) VALUES (?, ?) RETURNING id",
                          (last_channel(db), describe(tool_name, input))).fetchone()
    for _ in range(APPROVAL_TIMEOUT):
        await asyncio.sleep(1)  # async, so other tool calls (send_message...) keep working
        status = db.execute("SELECT status FROM approvals WHERE id = ?", (approval["id"],)).fetchone()["status"]
        if status != "pending":
            break
    else:
        db.execute("UPDATE approvals SET status = 'expired' WHERE id = ?", (approval["id"],))
        status = "expired"
    if status == "approved":
        return {"behavior": "allow", "updatedInput": input}
    reason = "The person said no." if status == "denied" else "The person didn't answer in time."
    return {"behavior": "deny", "message": reason}


if __name__ == "__main__":
    # 0.0.0.0 in Docker, so the runner container can reach it (never published to the host).
    server.run("streamable-http", host=os.environ.get("MCP_HOST", "127.0.0.1"), port=8001)

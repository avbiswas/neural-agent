"""The only engine-specific code. To use Codex (or anything else), rewrite
run_agent(): run a prompt, optionally resume a session, return text + session id.
(Steering is optional: an engine that can't do it just never calls more_messages.)"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
AGENT_HOME = ROOT / "data" / "agent-home"   # the agent's own $HOME (and ~/.claude)
WORKSPACE = ROOT / "agent"                  # where the agent works
MEMORY = WORKSPACE / "memory"               # its memory across sessions (see agent/CLAUDE.md)

# Only the built-in tools the agent needs. Leaving out Claude Code's own
# scheduling/notification tools (CronCreate, ScheduleWakeup, PushNotification...)
# matters: they only live inside one session, so they'd silently never fire.
TOOLS = "Bash,Read,Edit,Write,Grep,Glob,WebSearch,WebFetch,Skill,ToolSearch,Task"

# Added on top of Claude Code's own system prompt. Only the last message of a
# turn reaches the person (see `result`); everything before it stays internal.
APPEND_SYSTEM_PROMPT = """\
You are a personal assistant that the person can reach at any time. You are not \
running all the time: a harness wakes you up for each incoming message or event, \
you handle it in one turn, and then you stop until the next one. The person talks \
to you through a chat app, and they only see the final message of each turn. \
Anything you write before or between tool calls is never shown to them. So make \
your final message a complete answer on its own: what you did, what you found, \
or what you need from them. Write it like a chat message, not a report.

You also have a send_message tool that messages the person immediately, while \
you're still working. Use it for one short heads-up before work that will take \
more than a minute, like web research, building a site or a multi-step task \
("On it, this will take a few minutes."). Skip it for quick answers. Don't \
narrate your steps with it, and don't repeat your final message, which they get \
anyway.

You can wake yourself up later with set_followup: for reminders, or to check \
back on something ("see if the build finished in 20 minutes"). For anything \
that repeats ("every morning", "each Monday") use create_schedule. When a timer \
fires, a fresh session of you gets its prompt. In that turn nobody is waiting \
for your final message and it is never delivered: if the person should hear \
something, say it with send_message. If there is nothing worth telling them, \
stay quiet."""


def read_env_file(*names):
    """Read KEY=value (or export KEY=value) lines from .env / .envrc."""
    values = {}
    for name in names:
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip().removeprefix("export ").strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
    return values


def agent_env():
    """A clean environment: nothing from your shell leaks in, and HOME points at
    the agent's own home, so Claude Code ignores your plugins, skills, MCP, CLAUDE.md."""
    config = {**read_env_file(".env", ".envrc"), **os.environ}
    token = config.get("CLAUDE_CODE_OAUTH_TOKEN")
    if not token:
        sys.exit("No CLAUDE_CODE_OAUTH_TOKEN. Run `claude setup-token` and put it in .env")
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(AGENT_HOME),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "TERM": os.environ.get("TERM", "xterm-256color"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "CLAUDE_CODE_OAUTH_TOKEN": token,          # subscription login via `claude setup-token`
        "DISABLE_AUTOUPDATER": "1",                # don't install updates into the agent's home
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",    # memory is ours to build, not Claude Code's
        # Where the agent's sites are reachable (the sites skill prints links with it).
        "SITES_URL": config.get("SITES_URL", "http://127.0.0.1:8080"),
    }


def mcp_config(channel):
    """Our MCP server (harness_mcp.py), started by Claude Code for this run.
    Its tools show up to the agent as mcp__harness__<tool>."""
    return {"mcpServers": {"harness": {
        "command": sys.executable,  # this project's Python, which has the mcp package
        "args": [str(ROOT / "harness_mcp.py")],
        "env": {"HARNESS_CHANNEL": channel},
    }}}


def trust_workspace():
    """Claude Code ignores a project's .claude/settings.json until you accept a
    one-time "trust this folder" dialog. This is the agent's own home, so we
    record that answer for it directly."""
    path = AGENT_HOME / ".claude.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    project = data.setdefault("projects", {}).setdefault(str(ROOT), {})
    if not project.get("hasTrustDialogAccepted"):
        project["hasTrustDialogAccepted"] = True
        path.write_text(json.dumps(data, indent=2))


def run_agent(prompt, session_id=None, more_messages=lambda: [], channel="cli"):
    """Run one turn. session_id=None starts a new session, otherwise resumes it.
    channel is where the agent's send_message tool delivers ('cli', 'telegram').

    Steering: while the turn runs we call more_messages() about once a second.
    Any texts it returns are written to the running process, and Claude reads
    them at its next step, so the user can redirect a turn that's in progress."""
    AGENT_HOME.mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(exist_ok=True)
    trust_workspace()
    # Start with empty memory files the first time; the agent fills them in.
    (MEMORY / "notes").mkdir(parents=True, exist_ok=True)
    for name, heading in [("instructions.md", "# Standing orders"), ("index.md", "# Memory index")]:
        if not (MEMORY / name).exists():
            (MEMORY / name).write_text(heading + "\n")

    # stream-json in both directions: user messages go in on stdin as JSON
    # lines, and events come out on stdout as JSON lines. The process lives
    # until we close stdin.
    command = ["claude", "-p", "--input-format", "stream-json",
               "--output-format", "stream-json", "--verbose",
               "--model", "sonnet", "--tools", TOOLS,
               "--append-system-prompt", APPEND_SYSTEM_PROMPT,
               "--mcp-config", json.dumps(mcp_config(channel))]
    # What the agent may do without asking lives in agent/.claude/settings.json.
    if session_id:
        command += ["--resume", session_id]
    proc = subprocess.Popen(command, cwd=WORKSPACE, env=agent_env(), text=True,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def send(text):
        proc.stdin.write(json.dumps({"type": "user",
                                     "message": {"role": "user", "content": text}}) + "\n")
        proc.stdin.flush()

    # A background thread reads stdout, so the loop below can also check for
    # new messages while Claude is busy.
    lines = queue.Queue()
    def read_stdout():
        for line in iter(proc.stdout.readline, ""):
            lines.put(line)
        lines.put(None)  # process exited
    threading.Thread(target=read_stdout, daemon=True).start()

    send(prompt)
    results, last_check, deadline = [], 0, time.time() + 600
    context_tokens = 0  # size of the conversation at the latest model call
    while True:
        if not proc.stdin.closed and time.time() - last_check >= 1:
            for text in more_messages():
                send(text)
            last_check = time.time()
        if time.time() > deadline:
            proc.kill()
            raise RuntimeError("agent timed out")
        try:
            line = lines.get(timeout=0.2)
        except queue.Empty:
            continue
        if line is None:
            break
        event = json.loads(line)
        if event["type"] == "assistant" and event["message"].get("usage"):
            u = event["message"]["usage"]
            context_tokens = (u["input_tokens"] + u.get("cache_creation_input_tokens", 0)
                              + u.get("cache_read_input_tokens", 0) + u["output_tokens"])
        if event["type"] == "result":
            results.append(event)
            # The turn is over: closing stdin tells claude to exit. (A message
            # that slipped in just before this still gets its own result.)
            if not proc.stdin.closed:
                proc.stdin.close()

    proc.wait()
    if not results:
        raise RuntimeError("agent exited without a result")
    if results[-1].get("is_error"):
        error = results[-1].get("result") or "; ".join(results[-1].get("errors", []))
        # The saved session is gone (deleted, or a different machine): start fresh.
        if session_id and "No conversation found" in error:
            print("agent: session not found, starting a new one")
            return run_agent(prompt, None, more_messages)
        raise RuntimeError(error)
    usage = [r["usage"] for r in results]
    return {
        "text": "\n\n".join(r["result"] for r in results),
        "session_id": results[-1]["session_id"],
        "cost_usd": sum(r.get("total_cost_usd") or 0 for r in results),
        "input_tokens": sum(u["input_tokens"] + u["cache_creation_input_tokens"]
                            + u["cache_read_input_tokens"] for u in usage),
        "output_tokens": sum(u["output_tokens"] for u in usage),
        "context_tokens": context_tokens,
    }


if __name__ == "__main__":
    print(run_agent(" ".join(sys.argv[1:]) or input("Enter your prompt> ")))

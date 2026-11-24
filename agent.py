"""The only engine-specific code. To use Codex (or anything else), rewrite
run_agent(): run a prompt, optionally resume a session, return text + session id."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
AGENT_HOME = ROOT / "data" / "agent-home"   # the agent's own $HOME (and ~/.claude)
WORKSPACE = ROOT / "agent"                  # where the agent works

# Only the built-in tools the agent needs. Leaving out Claude Code's own
# scheduling/notification tools (CronCreate, ScheduleWakeup, PushNotification...)
# matters: they only live inside one session, so they'd silently never fire.
TOOLS = "Bash,Read,Edit,Write,WebSearch,WebFetch,Skill,ToolSearch,Task"


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
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or read_env_file(".env", ".envrc").get(
        "CLAUDE_CODE_OAUTH_TOKEN"
    )
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
    }


def run_agent(prompt, session_id=None):
    """Run one turn. session_id=None starts a new session, otherwise resumes it."""
    AGENT_HOME.mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(exist_ok=True)

    command = ["claude", "-p", prompt, "--output-format", "json",
               "--model", "sonnet", "--tools", TOOLS]
    if session_id:
        command += ["--resume", session_id]

    result = subprocess.run(command, cwd=WORKSPACE, env=agent_env(),
                            capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)

    data = json.loads(result.stdout)
    usage = data["usage"]
    return {
        "text": data["result"],
        "session_id": data["session_id"],
        "cost_usd": data.get("total_cost_usd"),
        "input_tokens": usage["input_tokens"]
        + usage["cache_creation_input_tokens"]
        + usage["cache_read_input_tokens"],
        "output_tokens": usage["output_tokens"],
    }


if __name__ == "__main__":
    print(run_agent(" ".join(sys.argv[1:]) or input("Enter your prompt> ")))

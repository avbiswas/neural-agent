import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
AGENT_HOME = ROOT / "data" / "agent-home"   # the agent's own $HOME (and ~/.claude)
WORKSPACE = ROOT / "agent"                  # where the agent works


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


token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or read_env_file(".env", ".envrc").get(
    "CLAUDE_CODE_OAUTH_TOKEN"
)
if not token:
    sys.exit("No CLAUDE_CODE_OAUTH_TOKEN. Run `claude setup-token` and put it in .env")

prompt = " ".join(sys.argv[1:]) or input("Enter your prompt> ")

AGENT_HOME.mkdir(parents=True, exist_ok=True)
WORKSPACE.mkdir(exist_ok=True)

# A clean environment: nothing from your shell leaks in (API keys, cloud creds...),
# and HOME points at the agent's own home, so Claude Code starts with a fresh
# ~/.claude: none of your plugins, skills, MCP servers, CLAUDE.md or settings.
env = {
    "PATH": os.environ["PATH"],
    "HOME": str(AGENT_HOME),
    "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    "TERM": os.environ.get("TERM", "xterm-256color"),
    "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    "CLAUDE_CODE_OAUTH_TOKEN": token,  # subscription login via `claude setup-token`
    "DISABLE_AUTOUPDATER": "1",        # don't install updates into the agent's home
}

# Only the built-in tools the agent needs. Leaving out Claude Code's own
# scheduling/notification tools (CronCreate, ScheduleWakeup, PushNotification...)
# matters: they only live inside one session, so they'd silently never fire.
TOOLS = "Bash,Read,Edit,Write,WebSearch,WebFetch,Skill,ToolSearch,Task"

result = subprocess.run(
    ["claude", "-p", prompt, "--output-format", "json", "--model", "sonnet",
     "--tools", TOOLS],
    cwd=WORKSPACE,
    capture_output=True,
    text=True,
    env=env,
    timeout=300,
)

if result.returncode != 0:
    print("claude failed:", result.stderr or result.stdout)
    sys.exit(1)

data = json.loads(result.stdout)
usage = data["usage"]

print("\nAgent: ", data["result"], "\n")
print({
    "session_id": data["session_id"],
    "cost_usd": data.get("total_cost_usd"),
    "duration_ms": data.get("duration_ms"),
    "turns": data.get("num_turns"),
})
print({
    "input_tokens": usage["input_tokens"],
    "cache_write_tokens": usage["cache_creation_input_tokens"],
    "cache_read_tokens": usage["cache_read_input_tokens"],
    "output_tokens": usage["output_tokens"],
    "thinking_tokens": usage.get("output_tokens_details", {}).get("thinking_tokens"),
})

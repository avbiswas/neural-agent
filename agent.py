import json
import os
import subprocess
import sys

prompt = " ".join(sys.argv[1:]) or input("Enter your prompt> ")

# Use the Claude subscription login, not API billing:
# if ANTHROPIC_API_KEY is set, claude -p silently prefers it.
env = dict(os.environ)
env.pop("ANTHROPIC_API_KEY", None)

result = subprocess.run(
    ["claude", "-p", prompt, "--output-format", "json", "--model", "sonnet"],
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

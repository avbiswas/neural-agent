"""The harness's MCP server: tools that let the agent act on the harness itself.
Claude Code starts it for each run (see --mcp-config in agent.py).

For now one tool: send_message. Timers come in a later stage.
"""
import os

from mcp.server.mcpserver import MCPServer

from db import connect

server = MCPServer("harness")
CHANNEL = os.environ["HARNESS_CHANNEL"]  # where this run's messages go, set by agent.py


@server.tool()
def send_message(text: str) -> str:
    """Send the person a chat message right now, in the middle of your turn.
    Your final message is delivered anyway, so don't use this to repeat it.
    Use it sparingly: e.g. a short heads-up before a task that will take a while."""
    connect().execute("INSERT INTO outbox (channel, text) VALUES (?, ?)", (CHANNEL, text))
    return "sent"


if __name__ == "__main__":
    server.run()  # speaks MCP over stdin/stdout

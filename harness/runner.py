"""The runner: the only place the agent (claude) runs. In Docker it has its
own container, with the workspace and the agent's home, and nothing else: no
database, no Telegram token, no keys of yours.

The worker connects, sends claude's arguments as one JSON line, and from then
on the connection is claude's stdin and stdout.

    uv run python -m harness.runner
"""
import json
import os
import socketserver
import subprocess
import threading

from harness.agent import WORKSPACE, agent_env, prepare_home

HOST = os.environ.get("RUNNER_HOST", "127.0.0.1")  # 0.0.0.0 in Docker (compose network only)


class Run(socketserver.StreamRequestHandler):
    def handle(self):
        args = json.loads(self.rfile.readline())
        prepare_home()
        claude = subprocess.Popen(["claude", *args], cwd=WORKSPACE, env=agent_env(),
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        print(f"runner: claude started (pid {claude.pid})")

        def to_claude():  # worker -> claude, until the worker closes its side
            for line in self.rfile:
                claude.stdin.write(line)
                claude.stdin.flush()
            claude.stdin.close()
        threading.Thread(target=to_claude, daemon=True).start()

        try:
            for line in claude.stdout:  # claude -> worker
                self.wfile.write(line)
        finally:
            claude.kill()  # the worker hung up (timeout) or claude finished: make sure it's gone
            print(f"runner: claude finished (exit {claude.wait()})")


socketserver.ThreadingTCPServer.allow_reuse_address = True
print(f"runner: waiting for the worker on {HOST}:9000")
socketserver.ThreadingTCPServer((HOST, 9000), Run).serve_forever()

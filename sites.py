"""Serve the agent's sites (agent/sites/) on 127.0.0.1:8080, each with a chat
button for talking to the agent about that page.

    uv run sites.py
    tailscale serve --bg 8080    # once, on the server: https://<server>.<tailnet>.ts.net/

127.0.0.1 means nothing else on your network can reach it. Tailscale Serve
forwards to it, so only devices on your tailnet can open the pages.

Site chat: every HTML page gets a chat widget (we add it as we serve the
page, so the agent doesn't have to). It's a conversation of its own, separate
from your main chat: the agent can answer questions about the page, look
things up, and change the page when you ask. Pick Sonnet or Opus in the widget.
"""
import functools
import http.server
import json
import os
import secrets
from pathlib import Path

from agent import WORKSPACE, run_agent
from history import log

SITES = Path(__file__).parent / "agent" / "sites"
SITES.mkdir(parents=True, exist_ok=True)
HOST = os.environ.get("SITES_HOST", "127.0.0.1")  # 0.0.0.0 inside Docker; compose publishes it on 127.0.0.1

WIDGET = (Path(__file__).parent / "site_chat.js").read_text()
CHAT_TOOLS = "Read,Edit,Write,Grep,Glob,WebSearch,WebFetch"  # no shell
# Paths as the runner sees them: a site chat must not touch memory or instructions.
KEEP_OUT = [f"{tool}(/{WORKSPACE}/{path})" for tool in ("Edit", "Write")
            for path in ("memory/**", "CLAUDE.md")]
CHAT_PROMPT = """\
You're chatting with the person about one of their private web pages, which \
you (their assistant) made. This is a side conversation, separate from their \
main chat. Answer questions about the page, look things up on the web, and \
change the page when they ask: make small edits to the files in its folder, \
and never touch anything outside that folder. After a change, say in a \
sentence what you changed: they get a button to reload the page. Keep answers \
short and conversational, like chat messages."""
chats = {}  # chat id (given to the browser) -> {"session", "model", "history"}


def status(event):
    """A short line about what the agent is doing, from a tool call."""
    if event["type"] != "assistant":
        return None
    for block in event["message"]["content"]:
        if block.get("type") != "tool_use":
            continue
        name, args = block["name"], block["input"]
        file = Path(args.get("file_path", "")).name
        return {"Read": f"Reading {file}", "Edit": f"Editing {file}", "Write": f"Writing {file}",
                "Grep": "Searching the page", "Glob": "Looking at the files",
                "WebSearch": f"Searching the web: {args.get('query', '')}",
                "WebFetch": f"Opening {args.get('url', '')}"}.get(name, f"Using {name}")


def last_change(folder):
    """When anything in a site's folder last changed (to offer a reload)."""
    return max((p.stat().st_mtime for p in folder.rglob("*") if p.is_file()), default=0)


class Sites(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/_chat.js":
            return self.reply(WIDGET.encode(), "text/javascript")
        path = Path(self.translate_path(self.path))
        if path.is_dir() and self.path.endswith("/"):
            path = path / "index.html"
        if path.suffix == ".html" and path.is_file():
            # The page as written, plus our chat widget.
            page = path.read_bytes() + b'\n<script src="/_chat.js"></script>\n'
            return self.reply(page, "text/html; charset=utf-8")
        super().do_GET()  # everything else as is (and /folder -> /folder/ redirects)

    def do_POST(self):
        if self.path != "/_chat":
            return self.send_error(404)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        model = "opus" if body.get("model") == "opus" else "sonnet"
        site = body["page"].strip("/").split("/")[0]
        folder = SITES / site
        if not site or site.startswith(".") or not folder.is_dir():
            return self.send_error(400, "Chat works on a site's pages")
        chat_id = body.get("chat") if body.get("chat") in chats else secrets.token_urlsafe(12)
        chat = chats.setdefault(chat_id, {"session": None, "model": model, "history": []})

        if chat["session"] and chat["model"] == model:
            prompt = body["message"]  # same conversation, same model: just continue
        else:
            # A new session: the first message, or a switch of model (a session
            # stays on one model). Tell it which page, and what was said so far.
            page = f"sites/{body['page'].lstrip('/')}" + ("index.html" if body["page"].endswith("/") else "")
            earlier = "\n\n".join(f"Person: {q}\nYou: {a[:1500]}" for q, a in chat["history"][-3:])
            prompt = (f"[Site chat] The person is looking at {page} (its folder: sites/{site}/). "
                      f"Read the page first.\n\n"
                      + (f"[Earlier in this chat, on another model]\n\n{earlier}\n\n" if earlier else "")
                      + f"[Their message]\n\n{body['message']}")
            chat.update(session=None, model=model)

        # Stream the answer as lines of JSON: status updates while it works, then the reply.
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        send = lambda data: (self.wfile.write((json.dumps(data) + "\n").encode()), self.wfile.flush())
        send({"chat": chat_id})
        before = last_change(folder)
        try:
            result = run_agent(prompt, chat["session"], model=model, tools=CHAT_TOOLS,
                               system=CHAT_PROMPT, harness=False,
                               extra=["--disallowedTools", *KEEP_OUT],
                               on_event=lambda e: (line := status(e)) and send({"status": line}))
            chat["session"] = result["session_id"]
            chat["history"].append((body["message"], result["text"]))
            log(f"site chat: {site} · {model}", body["message"], result["text"])
            send({"reply": result["text"], "changed": last_change(folder) != before})
        except Exception as error:
            send({"reply": f"Something went wrong: {error}", "error": True})

    def reply(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


handler = functools.partial(Sites, directory=SITES)
print(f"sites: serving agent/sites/ on http://{HOST}:8080")
http.server.ThreadingHTTPServer((HOST, 8080), handler).serve_forever()

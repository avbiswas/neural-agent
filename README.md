# NeuralAgent

A minimal always-on personal agent in Python, built to show how the pieces of an agent that lives on a server fit together: an inbox, timers, memory, permissions and an outbox, around Claude Code as the brain.

This is the repo for the Neural Breakdown video on building an always-on agent from scratch, based on Anthropic's "Building always-on agents". You can cycle through individual commits of this repo (`stage 1` to `stage 20`) and see how the full project came to life. The stages use a flat file layout, as built in the video; the last commits move the files into folders and add the docs.

**Want your own?** Follow [ONBOARDING.md](ONBOARDING.md): install Docker, run `./setup`, and you're chatting with it on Telegram in about 20 minutes, on your Mac or a small server.

## Features

- Chat with it on Telegram (or the terminal): messages are batched, and you can steer a turn while it's running.
- Remembers you: memory files it edits itself, a nightly "dream" that tidies them, and a searchable log of every conversation.
- Wakes itself up: one-off follow-ups and cron schedules ("every morning at 8, send me the weather").
- Private web pages on your Tailscale network, each with a chat button to ask about the page or change it.
- Approvals: anything that writes to outside systems (`git push`, deploys...) asks you first, with Approve / Deny buttons.
- Secrets: a private page for your API keys; the agent uses them one command at a time, and never sees the values in its output.
- Sonnet for everyday chat, handing heavy work (research, coding, sites) to an Opus subagent. Timers pick their model.
- Send it photos, PDFs and files.
- Backed up to two private GitHub repos through a GitHub App you own: its workspace (reviewed and committed hourly by the agent) and your conversations.
- Isolated: the agent runs in its own container with only the Claude login and the keys you give it. Nothing is published to the internet.

## How it works

```
 Telegram / terminal ──> inbox (SQLite) ──> worker ──> runner: claude -p (the agent)
                              ^                │              │
          scheduler (timers) ─┘                │              └─> MCP server: send_message,
                                               v                  timers, approvals
                                       outbox ──> Telegram / terminal
```

Every message, timer and command becomes a row in the inbox. The worker picks it up, runs the agent in its own container, and puts the reply in the outbox for the channel to deliver. The agent talks back to the harness through an MCP server: to message you mid-task, set timers, or ask for approval.

## Layout

| Folder | What's in it |
|---|---|
| `harness/` | the always-on loop: `worker`, `scheduler`, `runner` (where Claude runs), `agent` (the only engine-specific code), `db`, `mcp_server`, plus `dream`, `commit`, `history`, `github` and `agentctl` |
| `channels/` | `telegram` and `console`: messages in, replies out |
| `web/` | the private sites (with their chat widget) and the secrets page |
| `onboarding/` | the setup wizard behind `./setup`, terminal and web |
| `agent/` | the agent's own workspace: `CLAUDE.md`, skills, settings, and (at runtime) its memory, sites and uploads |
| `bin/`, `config/` | the `with-secrets` wrapper, and Tailscale's serve config |

Run it with `docker compose up -d` after `./setup`. Poke it from the terminal with `docker compose exec worker python -m harness.agentctl watch` (or `say "hi"`, `inbox`, `timers`).

## Support

If you find this helpful, consider supporting on Patreon — it hosts all code, projects, slides, and write-ups from the YouTube channel.

[<img src="https://c5.patreon.com/external/logo/become_a_patron_button.png" alt="Become a Patron!" width="200">](https://www.patreon.com/NeuralBreakdownwithAVB)

# Onboarding: set up your own always-on agent

About 20 minutes. You end up with an agent you can message on Telegram, that
runs on your server, keeps its files and your conversations backed up in two
private GitHub repos, and is reachable only from your own devices.

## What you need

- A server with Docker: a small Linux VPS (2 GB RAM is plenty) or, to try it
  out, your laptop.
- A Claude subscription (Pro or Max), and Claude Code on your laptop to create
  a login token.
- Telegram, a GitHub account, and Tailscale (free) on the server and your phone.

## 1. Get the code

    git clone <this repo> neural-agent && cd neural-agent

## 2. Fill in `.env`

Create `.env` next to `compose.yaml`. It never leaves the server, and each
service only gets the lines it needs.

    CLAUDE_CODE_OAUTH_TOKEN=...       # on your laptop: `claude setup-token`
    TELEGRAM_BOT_TOKEN=...            # message @BotFather on Telegram: /newbot
    TELEGRAM_CHAT_ID=...              # step 6 tells you this
    TZ=Europe/Berlin                  # your timezone, for "remind me at 6pm"
    SITES_URL=https://<server>.<tailnet>.ts.net
    SECRETS_URL=https://<server>.<tailnet>.ts.net:8443

## 3. Private access with Tailscale

Nothing is published to the internet. The agent's sites (port 8080) and your
secrets page (port 8081) listen on the server only; Tailscale makes them
reachable from your devices and nobody else's:

    tailscale serve --bg 8080                  # sites:   https://<server>.<tailnet>.ts.net
    tailscale serve --bg --https 8443 8081     # secrets: https://<server>.<tailnet>.ts.net:8443

Use `serve`, never `funnel` (funnel makes it public).

## 4. Create exactly two GitHub repos

| Repo | What goes in it | Written by |
|---|---|---|
| `agent-workspace` | the agent's files: memory, sites, skills, tools | the agent commits, the harness pushes |
| `agent-history` | your conversations, one markdown file a day | the harness only |

For both: **Private**, and **empty** (no README, no .gitignore, no license: the
first push must find nothing there). Any names work, as long as the
conversations repo ends in `-history` or `-chats`.

On github.com: **New repository**, or with the GitHub CLI:

    gh repo create agent-workspace --private
    gh repo create agent-history --private

## 5. Connect GitHub (a GitHub App that you own)

    docker compose run --rm --service-ports github-setup

Open http://localhost:8090. On a server, tunnel the port first from your
laptop: `ssh -L 8090:localhost:8090 you@server`.

1. **Create GitHub App.** GitHub shows the app pre-filled. Check it asks for
   only these permissions, then click **Create GitHub App**:
   - Repository contents: **Read and write** (to push the backups)
   - Metadata: **Read-only** (required by GitHub for every app)
   - No webhooks, and installable only on your account.
2. **Install.** Choose **Only select repositories** and pick exactly
   `agent-workspace` and `agent-history`. Not "All repositories".
3. The page says which repo gets what. Done: the setup container exits.

What this app can do: read and write code in those two repos. What it can't:
see any other repo, create or delete repos, change settings, or force-push
(the harness never forces, so your history can't be rewritten).

The app's private key stays on your server, in a volume the agent can't read.
Each push uses a fresh token that lasts an hour and covers one repo.

## 6. Start it

    docker compose up -d --build

Message your bot on Telegram. The first time, it ignores you and logs your chat
id: `docker compose logs telegram`. Put it in `.env` as `TELEGRAM_CHAT_ID`, run
`docker compose up -d` again, and say hi.

## 7. Check that everything works

| Try | Expect |
|---|---|
| "hi" on Telegram | 👀, then a reply |
| `/commit` | `Backup: pushed to agent-workspace` and `Chat log: pushed to agent-history` |
| "make me a page comparing 3 laptops" | a link to a page on your tailnet, with a chat button |
| "push the workspace with git push" | an Approve / Deny message (writes to outside systems ask first) |
| open the secrets page | your saved keys, by name only |

## Who can reach what

| | The agent | The harness |
|---|---|---|
| Claude login | yes (it runs on it) | no |
| Telegram token | no | the Telegram service only |
| GitHub app key | no | yes |
| Keys from the secrets page | yes, one command at a time, with your approval | no |
| Conversation log | read only | writes it |

## Later

- **Give the agent another repo:** GitHub, Settings, Applications, your app,
  Configure, add the repo. No restart.
- **More permissions** (e.g. pull requests): edit the app under Settings,
  Developer settings, GitHub Apps, then accept the request on the installation.
- **Cut it off:** uninstall or delete the app on GitHub. Every token stops
  working within the hour.
- **API keys for the agent** (Fly, Vercel...): it asks you with a link to the
  secrets page when it needs one.

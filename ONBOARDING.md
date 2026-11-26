# Set up your own always-on agent

You'll end up with a personal AI assistant that you message on Telegram. It
runs all the time on your computer or on a small server, remembers what you tell it,
can build private web pages for you, and backs itself up to your GitHub.
Only you can reach it.

It takes about 20 minutes. You don't need to know how to code: you'll copy a
few commands and paste a few keys.

## Before you start: the accounts

| | What for | Cost |
|---|---|---|
| **Claude** (Pro or Max) | the brain | your subscription |
| **Telegram** on your phone | how you talk to it | free |
| **Tailscale** | so its pages open only on your devices | free |
| **GitHub** | backups (optional, can be done later) | free |
| **A server** (only if it should run when your computer is off) | see Option B | about €4 a month |

Install Tailscale on your phone and your laptop now, and sign in on both with
the same account: https://tailscale.com/download

## Option A: run it on your computer

Works on macOS, Linux and Windows.

1. **Install Docker Desktop** from https://www.docker.com/products/docker-desktop/
   and open it (wait until it says it's running). On Linux you can install
   Docker Engine instead: `curl -fsSL https://get.docker.com | sh`, then
   `sudo usermod -aG docker $USER` and log out and back in.
2. **Open a terminal.** macOS: the Terminal app. Linux: your usual terminal.
   Windows: install WSL once (in PowerShell: `wsl --install`, then restart),
   open **Ubuntu** from the Start menu, and in Docker Desktop's settings turn
   on Resources, WSL integration, Ubuntu. Run everything below in Ubuntu.
3. **Download the agent.** Paste:

       git clone https://github.com/avbiswas/neural-agent.git
       cd neural-agent

   (If it says `git` isn't installed: on macOS, click Install when asked and
   paste the lines again; on Linux or WSL, run `sudo apt install -y git` first.)
4. **Run setup:**

       ./setup

   Prefer clicking to typing? Run `./setup --web` and open
   http://localhost:8090 instead. Same steps.

The agent runs while your computer is awake and Docker is running.

## Option B: run it on a server (always on)

1. **Rent a server.** At https://www.hetzner.com/cloud: create a project, Add
   Server, location close to you, image **Ubuntu 24.04**, type **CX22**. Under
   SSH keys, either add yours or skip it (Hetzner then emails you a root
   password). Create. Note the server's IP address.
2. **Log in** from your laptop's terminal. The `-L` part makes setup's web page
   and the GitHub step open in your laptop's browser:

       ssh -L 8090:localhost:8090 root@<SERVER-IP>

3. **Install Docker and download the agent:**

       curl -fsSL https://get.docker.com | sh
       git clone https://github.com/avbiswas/neural-agent.git
       cd neural-agent

4. **Run setup:**

       ./setup

   (or `./setup --web` and open http://localhost:8090 on your laptop).

## What setup asks you

Each answer is checked right away, so a typo can't slip through.

1. **Claude login.** Setup shows a link: open it, log in to Claude, paste the
   code back. Then paste the token it prints (starts with `sk-ant-oat`).
2. **Telegram.** On Telegram, open **@BotFather**, send `/newbot`, choose a
   name and a username ending in `bot`. Paste the token it gives you. Then
   send your new bot a message ("hi"): setup spots it, and from then on your
   agent answers only you.
3. **Timezone.** Already guessed, just confirm (e.g. `Europe/Berlin`).
4. **Tailscale.** In the Tailscale admin console:
   - DNS page (https://login.tailscale.com/admin/dns): turn on **MagicDNS**
     and **HTTPS Certificates**.
   - Keys page (https://login.tailscale.com/admin/settings/keys): **Generate
     auth key** with the default settings, and paste it.
5. **GitHub backups** (optional, you can skip and run `./setup` again later):
   - Create two **private, empty** repos (don't tick "Add a README"):
     `agent-workspace` (the agent's files) and `agent-history` (your
     conversations). Setup's page has links that fill in the form for you.
   - Click **Create GitHub App** on setup's page. GitHub shows the app with
     everything filled in: click **Create GitHub App**.
   - GitHub asks where to install it: choose **Only select repositories**
     and pick exactly those two repos. Click **Install**.

   The app can read and write code in those two repos only. It can't see
   your other repos, create or delete repos, or rewrite history.

When setup finishes, it prints your agent's private links:

    ✓ Your agent is running.
      Chat:        your Telegram bot (say hi!)
      Your pages:  https://agent.<your-tailnet>.ts.net
      Secrets:     https://agent.<your-tailnet>.ts.net:8443

## First things to try

- Say **hi** to your bot. You'll see 👀, then an answer.
- "Remind me to call mom in 10 minutes."
- "Every morning at 8, send me the weather in Berlin."
- "Make me a page comparing three laptops under €1000." You get a link, and
  the page has a chat button for questions and changes.
- Send it a photo or a PDF with a question.
- Anything that acts as you outside (pushing code, deploying) asks first, with
  Approve and Deny buttons.

## Good to know

- **Change anything:** run `./setup` again. It keeps what's set unless you
  replace it.
- **Stop / start:** `docker compose down` / `docker compose up -d` (in the
  `neural-agent` folder).
- **Something's off:** `docker compose logs -f worker` shows what the agent is
  doing; `docker compose logs telegram` shows the chat side.
- **Give it an API key** (say, to read your Fly logs): it asks you, with a link
  to your secrets page.
- **In Tailscale's admin console**, find the device called `agent` and choose
  **Disable key expiry**, or it gets logged out after six months.
- **Cut off GitHub:** on GitHub, Settings, Applications, uninstall the app.

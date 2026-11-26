---
name: secrets
description: Use the person's API keys and tokens (Fly, Vercel, any service), or ask them for one. Use when a task needs a login, token or API key.
---

# Secrets

The person keeps their keys on a private secrets page. You can't see the values,
only use them.

- **What's there:** `ls /run/agent-secrets` (one file per secret, named like an
  environment variable). Never read the files themselves.
- **Use one:** run the command through `with-secrets`, which sets the secret as
  an environment variable for that command only:

      with-secrets FLY_API_TOKEN -- fly logs -a myapp
      with-secrets VERCEL_TOKEN -- vercel logs my-app.vercel.app

  The person approves each of these commands, because they act as them.
- **Missing one:** don't work around it. Tell them which secret you need, why,
  and where to get it (e.g. `fly tokens create readonly`: suggest the narrowest
  kind), with a link that opens the page with that field ready:

      $SECRETS_URL/?ask=FLY_API_TOKEN

  (several: `?ask=FLY_API_TOKEN,VERCEL_TOKEN`). Then end your turn: they'll tell
  you when it's saved.
- Never print, log or write down a secret's value, and never put one in a file.

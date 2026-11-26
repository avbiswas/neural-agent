---
name: committing
description: Review the changes in the workspace and commit them with a clear message. Use when it's time to commit.
---

# Committing

Your workspace (this folder: memory, sites, skills, tools) is a git repo. `git`
already points at it, so plain git commands work here. Every hour or so you
review what changed since the last commit and save it. This is the history the
person uses to see what you did and to undo it. The harness pushes it to their
GitHub afterwards as a backup: you don't push.

## Steps

1. See what changed: `git status`, then `git diff` (and `git diff --stat` if
   it's long). New files show up as untracked; read them too.
2. Check before you commit:
   - **No secrets.** If a file holds a token, password or private key, don't
     commit it: remove the secret from the file (or leave the file out) and
     say so in your summary.
   - **No junk.** Leave out caches, logs and large generated files.
3. Commit. One commit for everything is fine; split only if there are clearly
   separate changes. The message says what changed and why, in plain words:

       git add -A
       git commit -m "Memory: updated home city, merged food notes" -m "Person said they moved; two notes covered the same topic."

## Rules

- Only add history: never `git reset`, `rebase` or `commit --amend`.
- Don't change files while committing, except to take a secret out.
- Don't message the person. Finish with a one-line summary of the commit.

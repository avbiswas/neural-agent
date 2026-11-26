"""Committing: every hour, if anything in agent/ changed, a fresh agent reviews
the changes and commits them with a good message (the committing skill, in
agent/.claude/skills/committing). Then the harness pushes the history to
GitHub as a backup.

    uv run python -m harness.commit     # by hand
    /commit                   # from chat; also runs hourly (see scheduler.py)
"""
import os
import subprocess

from harness import github
from harness.agent import ROOT, WORKSPACE, WORKSPACE_GIT, run_agent

BACKUP_GIT = ROOT / "data" / "workspace-backup.git"  # the harness's own copy, which it pushes


def has_changes():
    """`git status`, from the harness side, so a quiet hour costs no agent run.
    The repo's config is writable by the agent, so we switch off the settings
    that would make git run a command (fsmonitor) and never write the index."""
    env = {**os.environ, "GIT_DIR": str(WORKSPACE_GIT), "GIT_WORK_TREE": str(WORKSPACE),
           "GIT_OPTIONAL_LOCKS": "0"}
    status = subprocess.run(["git", "-c", "core.fsmonitor=false", "status", "--porcelain"],
                            env=env, capture_output=True, text=True)
    return status.returncode != 0 or status.stdout.strip() != ""


def backup_git(*args):
    return subprocess.run(["git", "--git-dir", str(BACKUP_GIT), *args],
                          capture_output=True, text=True)


def push():
    """Send the workspace history to GitHub, and say how it went.

    The agent never pushes and never sees a GitHub token. We copy its commits
    into a repo of our own (the agent controls its repo's config and hooks,
    which a push would run) and push from there. And we never force-push: if
    history was rewritten, GitHub refuses, so the backup can't be erased."""
    app = github.load_app()
    if not app:
        return "not backed up (GitHub isn't connected: see github.py)"
    if not BACKUP_GIT.exists():
        backup_git("init", "-q", "--bare", "-b", "main")
    if backup_git("fetch", "-q", f"file://{WORKSPACE_GIT}", "+main:main").returncode:
        return "nothing to back up yet"
    workspace, _ = github.pick_repos(app)
    if not workspace:
        return "not backed up (which repo is the workspace? see ONBOARDING.md)"
    return github.push(app, BACKUP_GIT, workspace)


def commit():
    """Commit if anything changed, then push. Returns (agent result or None, backup status)."""
    # A fresh session: it only needs the diff, not any conversation.
    result = run_agent("Time to commit. Use the committing skill to review what changed "
                       "in the workspace and commit it.") if has_changes() else None
    return result, push()


if __name__ == "__main__":
    result, backup = commit()
    print(result["text"] if result else "Nothing changed.")
    print("Backup:", backup)

"""Dreaming: a separate run that reviews what the person said since the last
dream and updates memory/ to match. The strategy is in the dreaming skill
(agent/.claude/skills/dreaming); this file only starts the run.

    uv run dream.py           # by hand
    /dream                    # from chat; also runs nightly (see scheduler.py)
"""
from datetime import datetime, timezone

from agent import MEMORY, ROOT, run_agent

LAST_DREAM = ROOT / "data" / "last-dream"  # when the last dream started (UTC)

# The two memory files loaded into every session (see agent/CLAUDE.md). Every
# character in them is paid for on every run, so they get a size limit.
LIMITS = {"instructions.md": 2000, "index.md": 3000}  # characters, ~4 per token


def oversized():
    """['memory/index.md is 4210 characters, the limit is 3000', ...]"""
    problems = []
    for name, limit in LIMITS.items():
        size = len((MEMORY / name).read_text())
        if size > limit:
            problems.append(f"memory/{name} is {size} characters, the limit is {limit}")
    return problems


def dream():
    since = LAST_DREAM.read_text().strip() if LAST_DREAM.exists() else "1970-01-01T00:00:00Z"
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # A fresh session every time: a dream works from the transcripts and the
    # memory files, not from anything it remembers.
    result = run_agent(f"Time to dream. Use the dreaming skill to review what the "
                       f"person said since {since} and update memory/ to match.")
    LAST_DREAM.write_text(started)  # only after a dream that finished

    # The harness checks the agent's work: if the always-loaded files grew too
    # big, it resumes the dream session with a system message to slim them down.
    problems = oversized()
    if problems:
        print(f"dream: {'; '.join(problems)} -> asking for a cleanup")
        cleanup = run_agent(
            "[System check] " + "; ".join(problems) + ". These files are loaded into "
            "every session, so get them under the limit with small edits: move "
            "detailed or rarely needed orders out of instructions.md into a note "
            "(with a line in index.md), merge notes on related topics into one, and "
            "shorten index lines. Don't lose information, move it. Finish with a "
            "short summary of what you changed.", result["session_id"])
        result["text"] += "\n\nCleanup: " + cleanup["text"]
        result["cost_usd"] += cleanup["cost_usd"]
        if oversized():
            result["text"] += "\n\n(Still over the limit: " + "; ".join(oversized()) + ")"
    return result


if __name__ == "__main__":
    print(dream()["text"])

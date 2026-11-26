---
name: dreaming
description: Review what the person said since the last dream and update memory/ to match. Use when it's time to dream.
---

# Dreaming

You are tidying your long-term memory, like a programmer working through a
codebase: look things up, then make small, targeted edits. Don't message the
person while dreaming.

## Strategy

1. **Know what you have.** `memory/instructions.md` and `memory/index.md` are
   already in your context. Don't read every note up front: look one up when
   you need it.
2. **Read what the person said** since the last dream (the time is in your task):

       python3 .claude/skills/dreaming/transcripts.py messages <SINCE>

3. **For each message that tells you something lasting** (a fact about them, a
   preference, a standing order, a correction, a decision, an ongoing project):
   - Search memory for it first: Grep `memory/` for a few related words, then
     Read the matching note.
   - If a message is unclear on its own ("yes", "the second one"), see what it
     answered:

         python3 .claude/skills/dreaming/transcripts.py context <REF>

4. **Change memory with small edits.**
   - Already there and still true: leave it.
   - Changed: Edit just that line. Newer beats older.
   - No longer true: remove that line (and the note, if it's now empty).
   - New, on an existing topic: add a line to that note.
   - New topic: Write a new `memory/notes/<topic>.md` and add one line for it
     to `memory/index.md`.
   - Standing orders ("always…", "never…", "from now on…") go in
     `memory/instructions.md`.
   Make changes with the Edit and Write tools, not shell commands, and never
   rewrite a whole file to change part of it.
5. **Tidy up.** Merge notes on the same topic, and keep `index.md` to one
   short line per note.

## Rules

- Only what the person said counts. Your own replies are there for context;
  they are not facts about the person.
- Skip small talk, one-off requests, and anything that can be looked up again
  (for a site or repo, keep a pointer, not a copy).
- Finish with a short summary of what you changed, or "Nothing new to remember."

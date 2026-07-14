---
name: planning-context
description: Use at the start of EVERY session and before ending any work session in a repo with a .planning/ directory — restores project memory from markdown files that survive /clear, and writes state back so no context is ever lost. Also use when the user says "where were we", "resume", "update the plan", or after context compaction.
---

# Planning Context — External Project Memory

Project state lives in `.planning/` markdown files, NOT in the context window.
Conversation memory is disposable; these files are not. Emulates GSD's `.planning/`
layout (stay format-compatible) but without GSD process ceremony — superpowers
drives the actual work loop.

## On session start (or after /clear, compaction, "resume")

Read in order:

1. `.planning/STATE.md` — position, next action, session log, handoff notes
2. `.planning/ROADMAP.md` — milestones, phases, statuses, definition of done
3. `.planning/PROJECT.md` — vision, constraints, **decisions table** (never re-litigate
   a decided question; propose a new decision row instead)
4. As needed: `.planning/design/` (dated design docs), `.planning/codebase/` (maps),
   `.planning/todos/pending.md` (small items)

If chat context and `.planning/` disagree, `.planning/` wins until the user overrides.

## On session close, milestone, or before any risky/large change

Write back BEFORE ending:

- `STATE.md` — update Position + Next action; append dated session-log entry (3-6
  bullets: what happened, what changed, what's blocked)
- `ROADMAP.md` — flip phase statuses; add newly discovered phases to parking lot
- `PROJECT.md` — append new decisions: date, decision, why
- `todos/pending.md` — add/check off small items
- Commit `.planning/` changes together with the code they describe

## Rules

- Additions over rewrites: append to session log, never erase history
- Decisions need a "why" — a decision without rationale gets re-litigated
- Convert relative dates ("yesterday") to absolute (2026-07-14) when writing
- Keep entries terse and factual; this is memory, not documentation
- If `.planning/` doesn't exist yet, offer to bootstrap it with PROJECT.md, ROADMAP.md,
  STATE.md seeded from the current conversation

# AOH — Agentic Ops Harness

Engine-neutral harness for agentic ops: packs of skills/roles/teams compiled to agent
runtimes (Hermes today; Claude Code, Codex, Goose next). AOH organizes, packages,
validates, adapts — it never executes. Runtimes execute.

## Session bootstrap (ALWAYS, including after /clear or compaction)

Project memory lives in `.planning/` markdown, outside the context window. Before any
work:

1. Read `.planning/STATE.md` — current position, next action, handoff notes
2. Read `.planning/ROADMAP.md` — phase you're in, what "done" means
3. Consult `.planning/PROJECT.md` decisions table before proposing design changes —
   don't re-litigate decided questions; add new decisions to the table instead
4. `.planning/design/` holds dated design reviews; `.planning/codebase/` holds
   architecture/structure/concerns maps; `.planning/todos/pending.md` holds small items

Never rely on conversation memory for project state. If chat and `.planning/` disagree,
`.planning/` wins until the user says otherwise.

## Session close (or any significant milestone)

Update `.planning/` BEFORE ending work — this is how context survives /clear:

- `STATE.md`: position, session log entry (date + what happened), next action
- `ROADMAP.md`: phase status changes
- `PROJECT.md`: new decisions with date + why
- Commit `.planning/` changes with the work they describe

## Working style

Superpowers drives the loop — speed of iteration over ceremony:

- Creative/feature work → superpowers:brainstorming first
- All implementation → superpowers:test-driven-development (RED/GREEN/REFACTOR, no
  production code without a failing test)
- Bugs → superpowers:systematic-debugging
- Completion claims → superpowers:verification-before-completion (fresh command output
  or it didn't happen)

`.planning/` is shared memory, not process. Do NOT spin up GSD phase ceremony
(PLAN.md, verification docs) here — GSD files that already exist (`codebase/`) are
read-only reference; keep formats compatible so GSD tools still work.

## Conventions

- Python + uv. Run things via `uv run ...`
- Tests: `rtk proxy uv run pytest -q` (plain `rtk pytest` fails to collect in uv projects)
- Validate packs: `uv run aoh validate collections/core/docker-disk-cleanup examples/acme-platform-ops` (validate accepts one pack path at a time — run per pack)
- Semver tags; update `CHANGELOG.md` before every release
- Engine-neutral rule: no runtime-specific concepts in `pack.py`/spec — runtime knowledge
  belongs in `src/aoh/adapters/<runtime>.py` only
- Skills follow agentskills SKILL.md format (frontmatter `name` matches dir, `description`
  required)
- Progressive disclosure: only `AOH.yaml` + `skills/` are mandatory in a pack; everything
  else (agents, teams, models, evals, runtime-requirements) is opt-in — keep it that way

## Key architecture files

- `src/aoh/pack.py` — pack model + validator (referential integrity)
- `src/aoh/adapters/hermes.py` — Hermes adapter (profile generation)
- `src/aoh/cli.py` — CLI entrypoints
- `docs/spec.md` — pack spec (keep in sync with validator changes)

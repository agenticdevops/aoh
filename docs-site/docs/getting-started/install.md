---
title: Install
---

# Install

AOH is a Python/uv command-line tool. There is nothing to deploy and no server to
run — you install the CLI, point it at a pack directory, and it validates or
compiles that pack into a runtime-native shape.

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — AOH is run as `uv run aoh ...`; uv resolves
  the project's dependencies on the fly, so there's no separate `pip install` step.
- **Node.js** — only if you plan to build or run this documentation site locally.
  Not required for AOH itself.

You do **not** need Hermes, kubectl, or any other runtime installed to validate
packs or generate adapter output. Those only matter once you want to actually
launch an agent (see [Your First Agent](./first-agent)).

## Clone the repository

```bash
git clone https://github.com/agenticdevops/aoh.git
cd aoh
```

## Confirm the CLI works

```bash
uv run aoh --help
```

Expected output:

```text
usage: aoh [-h]
           {validate,init-pack,adapt-hermes,install-hermes,install-hermes-agent,install-hermes-team}
           ...

positional arguments:
  {validate,init-pack,adapt-hermes,install-hermes,install-hermes-agent,install-hermes-team}
    validate            Validate an AOH pack
    init-pack           Create a starter AOH pack
    adapt-hermes        Generate a Hermes-native view
    install-hermes      Install AOH pack skills into a Hermes skills directory
    install-hermes-agent
                        Create a launchable Hermes profile for an AOH pack
    install-hermes-team
                        Create Hermes profiles for every role in an AOH team

options:
  -h, --help            show this help message and exit
```

If that printed, you're set — no further installation step exists. Everything else
is `uv run aoh <subcommand>` against a pack directory in your working tree or checked
out from Git.

## What `aoh` actually is

If you've used `ansible-galaxy` or the `terraform` CLI, the mental model transfers
directly: `uv run aoh` is the entrypoint for a small, focused set of subcommands that
operate on a declarative directory (a **pack**) instead of a live target. AOH never
executes anything against your infrastructure itself — it validates packs and
compiles (**adapts**) them into files a runtime like Hermes can load. The runtime
does the executing.

The full subcommand surface, all of it:

| Command | What it does |
|---|---|
| `validate` | Check a pack's structure and referential integrity |
| `init-pack` | Scaffold a new starter pack |
| `install` | Install a pack for a runtime — `hermes`, `claude-code`, or `codex` (all shipped) |
| `adapt-hermes` | Generate a Hermes-native view of a pack (files only, no install) |
| `install-hermes` | Install a pack's skills into a Hermes skills directory |
| `install-hermes-agent` | Create a launchable Hermes profile for a pack or role |
| `install-hermes-team` | Create one Hermes profile per role in a team |

`aoh install --runtime <hermes|claude-code|codex>` exists and is the runtime-neutral
entrypoint — see [Adapters](../reference/adapters) for what each runtime generates.
Drift detection (`aoh status` / `sync` / `capture`) and a standalone eval runner are
still roadmap, not implemented.

## Minimum viable pack

A pack needs exactly two things to be valid:

- `AOH.yaml` — pack metadata (name, description, owner)
- `skills/` — at least one skill directory containing a `SKILL.md`

Everything else — `roles/`, `teams/`, `models/`, `evals/`, `runtime-requirements/` —
is optional and additive. That's the whole point: you can go from an empty
directory to a validated, adapter-ready pack in about five minutes. The next page
walks through exactly that.

## Next

[Your First Pack](./first-pack) — validate a real pack and scaffold your own.

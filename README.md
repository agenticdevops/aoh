# AOH: Agentic Ops Harness

**Superpowers for Ops.** AOH is an engine-neutral harness for building, sharing, and running agentic DevOps, SRE, Platform Engineering, and MLOps capabilities.

**Docs:** the full docs site (Concepts, Getting Started, Tutorials, Reference, and the
Field Notes blog) lives in [`docs-site/`](docs-site/) and is published at
[https://agenticdevops.github.io/aoh/](https://agenticdevops.github.io/aoh/).

Think of it as an early **Ansible-for-agentic-ops** pattern:

- Ansible has inventories, roles, and playbooks.
- AOH has orgs, teams, roles, skills (including process skills), runtime requirements, and adapters.
- Agent runtimes such as Hermes, Goose, Codex, Claude Code, and OpenCode become execution engines.

AOH ships three runtime adapters today: Hermes, Claude Code, and Codex.

## Why AOH?

Modern ops teams already work through roles:

- SREs triage incidents and protect reliability.
- DevOps engineers automate delivery and infrastructure changes.
- Platform engineers build paved roads.
- MLOps engineers operate training, inference, and model delivery systems.

Agentic tools should understand that structure.

AOH lets you model a real team once, keep it in Git, and compile it into runtime-native agent setups.

```text
Org / Business Unit / Project
  -> Team
    -> Role
      -> Skills / Capabilities (including process skills)
      -> Runtime Requirements
      -> Model Profile
  -> Runtime Adapter
    -> Hermes / Claude Code / Codex profiles today
    -> Goose / OpenCode later
```

## What Works Today

This MVP includes:

- A portable AOH pack format.
- Team, role, skill, model profile, runtime requirement, and eval artifacts.
- A Python/uv CLI for validation and adapter generation, including the
  runtime-neutral `aoh install --runtime <hermes|claude-code|codex>` entrypoint.
- Hermes, Claude Code, and Codex adapters that materialize launchable, runtime-native
  workspaces (Hermes profiles, Claude Code `.claude/` workspaces, Codex `.agents/` +
  `.codex/` workspaces).
- A realistic `acme-platform-ops` example with SRE, DevOps, and MLOps roles.
- A core `docker-disk-cleanup` vertical slice.

## Core Concepts

### Pack

A Git-backed source of truth for an agentic ops capability set.

### Team

A group mapped to an org, business unit, or project, such as `platform-ops`.

### Role

A real-world job function such as:

- `sre-platform`
- `devops-automation`
- `mlops-training`

Each role owns a specific set of skills, runtime requirements, and model intent.

### Skill

An agent-usable capability, written as `SKILL.md` with optional scripts and references.
A **process skill** is a plain skill whose body orchestrates other skills by name
(order, branching, escalation) — AOH's convention for repeatable operational flows.

### Adapter

The compiler from AOH’s portable model into a runtime’s native shape.

For Hermes:

```text
AOH Team -> multiple Hermes profiles
AOH Role -> one Hermes profile
AOH Skills -> profile-local Hermes skills
AOH Role instructions -> SOUL.md
AOH launch -> launch.sh
```

## Repository Layout

```text
.
├── collections/
│   └── core/docker-disk-cleanup/
├── examples/
│   └── acme-platform-ops/
│       ├── teams/
│       ├── roles/
│       ├── skills/
│       ├── models/
│       ├── runtime-requirements/
│       └── evals/
├── src/aoh/
├── tests/
└── docs/
```

## Quick Start

Install dependencies:

```bash
uv venv
uv sync --extra dev
```

Run tests:

```bash
uv run pytest -q
```

Validate the core pack:

```bash
uv run aoh validate collections/core/docker-disk-cleanup
```

Validate the team example:

```bash
uv run aoh validate examples/acme-platform-ops
```

## Run With Hermes

Create Hermes profiles for every role in the Acme Platform Ops team:

```bash
uv run aoh install-hermes-team examples/acme-platform-ops \
  --profiles-dir ~/.hermes/profiles \
  --team platform-ops \
  --profile-prefix acme-platform \
  --provider openai-codex \
  --model gpt-5.4 \
  --cwd "$PWD"
```

This creates role-specific Hermes profiles:

```text
acme-platform-sre-platform
acme-platform-devops-automation
acme-platform-mlops-training
```

Check the DevOps role:

```bash
hermes profile show acme-platform-devops-automation
hermes --profile acme-platform-devops-automation skills list
```

Launch the DevOps role-agent:

```bash
~/.hermes/profiles/acme-platform-devops-automation/launch.sh \
  -q "Answer in one sentence: what AOH role are you, and which AOH skills are associated with you?" \
  --max-turns 2 --quiet
```

Expected shape:

```text
I’m the AOH DevOps Engineer for Acme Platform in the devops-automation role,
and my associated AOH skills are deployment-automation, terraform-plan-review,
and service-health-report.
```

## Create Your Own Pack

```bash
uv run aoh init-pack postgres-health-check \
  --output collections/local/postgres-health-check \
  --description "Check PostgreSQL health using read-only diagnostics."
```

Then add:

- team definitions under `teams/`
- role definitions under `roles/`
- skills under `skills/` (including process skills for multi-step flows)
- runtime requirements under `runtime-requirements/`
- evals under `evals/`

Validate:

```bash
uv run aoh validate collections/local/postgres-health-check
```

## CLI

```bash
uv run aoh --help
```

Current commands:

- `validate`: validate an AOH pack
- `init-pack`: create a starter pack
- `install --runtime <hermes|claude-code|codex>`: materialize a pack as a
  self-contained workspace for the given runtime (`--output` required; optional
  `--binding`, `--role`, `--profile`, `--model`, `--discard-local`)
- `install --site <dir>`: fan out an install across every binding in a site's
  inventory (optional `--group`, `--binding <name>`, `--workspace-root`,
  `--accept-site-root`, `--discard-local`); requires `aoh lock` first
- `list [--site <dir>]`: fleet table — binding, role, pack@ref, runtime,
  context/namespace, access, workspace path, provisioned/credential state
- `config init|get|set`: manage the user config (`~/.aoh/config.yaml`)
- `lock [--site <dir>] [--update [<pack>]] [--yes]`: resolve site pack refs to
  commits and write/update `site.lock.yaml`
- `adapt-hermes`: generate a Hermes-native file view
- `install-hermes`: install pack skills into a Hermes skills directory
- `install-hermes-agent`: create one launchable Hermes profile for a pack or role
- `install-hermes-team`: create one Hermes profile per role in a team

See [Runtime Adapters](docs/adapters.md) for what each `--runtime` generates,
including the threat model and honest guardrail gaps for Claude Code and Codex.
See [docs/installs.md](docs/installs.md) for the crash-safe convergent install
model every install path shares, and [docs/spec.md](docs/spec.md) for the
`UserConfig`/`Site`/`SiteLock` kinds behind the fleet commands.

## Roadmap

- Authoring/promote flow: draft a skill locally, `aoh skill promote` it into a
  pack repo.
- Pack registry, named/ordered, with a lockfile-backed integrity model
  (`site.lock.yaml` ships in v0.3 phase A; full registry in phase C).
- Drift: `aoh status` / `sync` / `capture` — compare a workspace against its
  manifest and the pack's current state.
- Fleet console: generate (never execute) a provisioning + kubeconfig bundle for
  operating an entire site in one Claude Code session.
- Goose adapter: skills, recipes, sub-recipes, extensions.
- OpenCode adapter.
- Eval runner for role/skill validation.
- Richer runtime requirement negotiation.
- Policy and approval metadata mapped into runtime-native guardrails.

## Philosophy

AOH does not try to replace your agent runtime.

It gives your ops organization a portable source of truth:

```text
who the agent is
what team it belongs to
what role it performs
what skills it has (including process skills it can run)
what tools it needs
which runtime should execute it
```

The runtime executes. AOH organizes, packages, validates, and adapts.

## License

MIT. See [LICENSE](LICENSE).

# AOH: Agentic Ops Harness

**Superpowers for Ops.** AOH is an engine-neutral harness for building, sharing, and running agentic DevOps, SRE, Platform Engineering, and MLOps capabilities.

Think of it as an early **Ansible-for-agentic-ops** pattern:

- Ansible has inventories, roles, and playbooks.
- AOH has orgs, teams, roles, skills, workflows, runtime requirements, and adapters.
- Agent runtimes such as Hermes, Goose, Codex, Claude Code, and OpenCode become execution engines.

AOH starts with Hermes Agent as the first working runtime adapter.

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
      -> Skills / Capabilities
      -> Workflows
      -> Runtime Requirements
      -> Model Profile
  -> Runtime Adapter
    -> Hermes profiles today
    -> Goose / Codex / Claude Code / OpenCode later
```

## What Works Today

This MVP includes:

- A portable AOH pack format.
- Team, role, skill, workflow, model profile, runtime requirement, and eval artifacts.
- A Python/uv CLI for validation and adapter generation.
- A Hermes adapter that creates launchable Hermes profiles.
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

Each role owns a specific set of skills, workflows, runtime requirements, and model intent.

### Skill

An agent-usable capability, written as `SKILL.md` with optional scripts and references.

### Workflow

The repeatable operational flow that composes skills, role, model profile, runtime requirements, and evals.

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
│       ├── agents/
│       ├── skills/
│       ├── workflows/
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
- role definitions under `agents/`
- skills under `skills/`
- workflows under `workflows/`
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
- `adapt-hermes`: generate a Hermes-native file view
- `install-hermes`: install pack skills into a Hermes skills directory
- `install-hermes-agent`: create one launchable Hermes profile for a pack or role
- `install-hermes-team`: create one Hermes profile per role in a team

## Roadmap

- Goose adapter: skills, recipes, sub-recipes, extensions.
- Codex adapter: `.agents/skills`, `AGENTS.md`, project/worktree conventions.
- Claude Code adapter: skills plus `CLAUDE.md` role/project instructions.
- OpenCode adapter.
- Pack registry and versioning.
- Eval runner for role/workflow validation.
- Richer runtime requirement negotiation.
- Policy and approval metadata mapped into runtime-native guardrails.

## Philosophy

AOH does not try to replace your agent runtime.

It gives your ops organization a portable source of truth:

```text
who the agent is
what team it belongs to
what role it performs
what skills it has
what workflows it can run
what tools it needs
which runtime should execute it
```

The runtime executes. AOH organizes, packages, validates, and adapts.

## License

MIT. See [LICENSE](LICENSE).

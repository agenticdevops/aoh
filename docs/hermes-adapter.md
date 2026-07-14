# Hermes Adapter

The Hermes adapter is the first AOH runtime adapter. It materializes an engine-neutral AOH pack into Hermes-friendly files without forking Hermes.

## Generated Output

```text
hermes-output/
  skills/<skill-name>/SKILL.md
  commands/ops-<skill-name>.md
  aoh-hermes.json
```

## Install Into Hermes

Install an AOH pack into the active Hermes profile skills directory:

```bash
uv run aoh install-hermes collections/core/docker-disk-cleanup \
  --skills-dir ~/.hermes/profiles/finops/skills
```

This writes:

```text
~/.hermes/profiles/finops/skills/aoh/docker-disk-cleanup/SKILL.md
~/.hermes/profiles/finops/skills/aoh/docker-disk-cleanup/references/aoh-pack.md
~/.hermes/profiles/finops/skills/aoh/docker-disk-cleanup/scripts/inspect_docker_disk.sh
~/.hermes/profiles/finops/skills/aoh/docker-disk-cleanup.aoh-hermes.json
```

Check that Hermes sees it:

```bash
hermes skills list | grep -i docker-disk-cleanup
```

Run a smoke test with Codex auth:

```bash
hermes chat --provider openai-codex -m gpt-5.4 --skills docker-disk-cleanup \
  -q "Using the preloaded docker-disk-cleanup skill, answer only the deterministic helper script path mentioned by the skill." \
  --max-turns 2 --quiet
```

Expected output:

```text
/Users/gshah/.hermes/profiles/finops/skills/aoh/docker-disk-cleanup/scripts/inspect_docker_disk.sh
```

## Create A Launchable Hermes Agent

AOH can create a Hermes profile that acts as the custom agent for a pack or a specific role. The profile contains:

- `config.yaml` with model/provider/tool settings
- `SOUL.md` with AOH role instructions
- profile-local AOH skills scoped to the role
- `aoh-agent.json` manifest
- `launch.sh` that preloads the associated skills

Create a pack-level agent:

```bash
uv run aoh install-hermes-agent collections/core/docker-disk-cleanup \
  --profiles-dir ~/.hermes/profiles \
  --profile aoh-docker-disk-cleanup \
  --provider openai-codex \
  --model gpt-5.4 \
  --cwd "$PWD"
```

Create a role-scoped org/project agent:

```bash
uv run aoh install-hermes-agent examples/acme-platform-ops \
  --profiles-dir ~/.hermes/profiles \
  --profile acme-platform-sre \
  --role sre-platform \
  --provider openai-codex \
  --model gpt-5.4 \
  --cwd "$PWD"
```

Create profiles for every role in a team:

```bash
uv run aoh install-hermes-team examples/acme-platform-ops \
  --profiles-dir ~/.hermes/profiles \
  --team platform-ops \
  --profile-prefix acme-platform \
  --provider openai-codex \
  --model gpt-5.4 \
  --cwd "$PWD"
```

This creates profiles such as:

```text
acme-platform-sre-platform
acme-platform-devops-automation
acme-platform-mlops-training
```

Verify the profile:

```bash
hermes profile show acme-platform-sre
hermes --profile acme-platform-sre skills list
```

Launch the custom agent:

```bash
~/.hermes/profiles/acme-platform-sre/launch.sh \
  -q "Answer in one sentence: what AOH role are you, and which AOH skills are associated with you?" \
  --max-turns 2 --quiet
```

Expected output:

```text
I’m the AOH SRE runtime for Acme Platform in the sre-platform role, and the associated AOH skills are service-health-report and docker-disk-cleanup.
```

## Mapping

- AOH `skills/` copy directly into Hermes-compatible skills, and each skill also gets
  a generated `commands/ops-<skill>.md` command.
- AOH `teams/` become groups of role-scoped Hermes profiles.
- AOH `roles/` become role guidance in `SOUL.md` and role-scoped profile skills.
- AOH `models/` are referenced as model intent until deeper Hermes profile installation is added.
- AOH `runtime-requirements/` are surfaced as runtime expectations.
- AOH `evals/` are listed in the adapter manifest for future test runners.

## Current Scope

The adapter can generate files, install skills into an explicit Hermes skills directory, create a launchable Hermes profile for a role, or create one profile per role in a team. It does not switch your sticky Hermes profile, create cron jobs, or start background services.

That keeps v0 safe and fast: AOH can validate and materialize packs while Hermes remains the runtime.

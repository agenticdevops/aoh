---
title: Your First Agent
---

# Your First Agent

The previous page generated Hermes *files* with `adapt-hermes`. This page goes
one step further and creates a launchable Hermes **profile** — a self-contained
agent identity with its own model config, instructions, and scoped skills.

## Install a Hermes agent profile

```bash
uv run aoh install-hermes-agent collections/core/kubeops \
  --profile kubeops-demo \
  --role kubeops-copilot
```

Expected output:

```text
installed Hermes agent profile in /Users/you/.hermes/profiles/kubeops-demo
```

(`~` in `--profiles-dir` is expanded to your actual home directory in the printed
path.) `--profiles-dir` defaults to `~/.hermes/profiles`; pass `--profiles-dir` explicitly
to write somewhere else (useful for trying this out without touching your real
Hermes setup, e.g. `--profiles-dir /tmp/hermes-profiles`).

## What got generated

```text
~/.hermes/profiles/kubeops-demo/
  config.yaml
  SOUL.md
  launch.sh
  aoh-agent.json
  skills/aoh/
    k8s-service-health-report/SKILL.md
    k8s-service-health-report/scripts/collect_health_summary.sh
    k8s-service-health-report/references/aoh-pack.md
    node-notready-triage/...
    pending-pod-triage/...
    pod-crashloop-triage/...
    kubeops.aoh-hermes.json
```

- **`config.yaml`** — model/provider/tool settings for this profile (provider,
  model, terminal backend, working directory, max turns).
- **`SOUL.md`** — the role's identity and instructions, generated from the AOH
  role. For `kubeops-copilot` this includes the role's stated responsibilities
  verbatim, e.g. *"recommend the smallest safe next action; never attempt
  mutations"* and *"report RBAC denials as guardrails working, not errors to work
  around."* This is the read-only posture: the profile is instructed to inspect
  and diagnose, not mutate, before it ever talks to a runtime requirement.
- **`skills/aoh/`** — the role's skills (only `kubeops-copilot`'s four skills,
  scoped to this profile — not the whole pack).
- **`launch.sh`** — a wrapper that calls `hermes --profile kubeops-demo --skills
  <role skills> chat "$@"`, so the profile always launches with the right skills
  preloaded.
- **`aoh-agent.json`** — manifest recording pack, role, profile name, provider,
  model, cwd, and skills for this install.

## Flags

`install-hermes-agent` only accepts the flags below — nothing else exists:

| Flag | Default | Purpose |
|---|---|---|
| `--profiles-dir` | `~/.hermes/profiles` | Where to write the profile |
| `--profile` | *(required)* | Profile name |
| `--provider` | `openai-codex` | Model provider |
| `--model` | `gpt-5.4` | Model name |
| `--cwd` | current directory | Working directory baked into `config.yaml` |
| `--category` | `aoh` | Skill namespace under `skills/` |
| `--role` | *(none — pack-level agent)* | Scope the profile to one role instead of the whole pack |
| `--binding` | *(none)* | Path to a Binding artifact for RBAC-scoped kubeconfig wiring (see the read-only tutorial) |

## Launching it

The artifacts above are generated regardless of whether Hermes itself is
installed — `install-hermes-agent` only writes files. To actually run the agent
you need Hermes on your machine, then:

```bash
~/.hermes/profiles/kubeops-demo/launch.sh -q "your question" --max-turns 2 --quiet
```

## Next

For the RBAC-scoped version of this same pack — a `Binding` that provisions a
least-privilege kubeconfig and wires it into the profile via `--binding` — see
[KubeOps Read-Only](../tutorials/kubeops-readonly).

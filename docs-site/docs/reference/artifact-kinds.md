---
title: Artifact Kinds
---

# Artifact Kinds

Seven kinds make up an AOH pack, plus `Binding` (which lives outside packs) — eight in all. Fields
below are taken from the loader dataclasses in
[`src/aoh/pack.py`](https://github.com/agenticdevops/aoh/blob/main/src/aoh/pack.py)
and cross-checked against [`docs/spec.md`](https://github.com/agenticdevops/aoh/blob/main/docs/spec.md).
Every example uses `apiVersion: openagentix.io/v1alpha2`.

## Pack

Top-level metadata and ownership. Lives at `AOH.yaml`, exactly one per pack. Required:
`apiVersion: openagentix.io/v1alpha2`, `kind: Pack`, `metadata.name`.

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Pack
metadata:
  name: docker-disk-cleanup
  displayName: Docker Disk Cleanup
  description: Read-only Docker disk usage triage.
```

## Skill

Agentskills-compatible instructions plus optional scripts/references/assets. Lives at
`skills/<skill-name>/SKILL.md`. At least one is required per pack. `SKILL.md` must
start with YAML frontmatter whose `name` matches the directory name and whose
`description` is non-empty.

```yaml
---
name: docker-disk-cleanup
description: Use when investigating high Docker disk usage and recommending safe cleanup steps.
---
```

A **process skill** is a plain `Skill` whose body orchestrates other skills by name
(order, branching, escalation) — there is no dedicated `ProcessSkill` kind. It's a
documented convention, not a schema.

## Role

An org/project job function with associated skills, runtime requirements, model
profile, and responsibilities. Lives at `roles/<role-name>.yaml`. Required:
`metadata.name`; `spec` fields are all optional but every referenced skill / runtime
requirement / model profile must exist in the pack (checked by `aoh validate`).

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Role
metadata:
  name: sre-platform
  displayName: SRE - Acme Platform
spec:
  org: acme
  project: platform
  purpose: Own platform reliability, incident triage, and safe remediation guidance.
  skills:
    - service-health-report
  runtimeRequirements:
    - shell-readonly
  modelProfile: worker-codex
  responsibilities:
    - diagnose platform health and reliability issues
```

## Team

Org/project/BU container that groups related operational roles. Lives at
`teams/<team-name>.yaml`. Required: `metadata.name`; every entry in `spec.roles` must
exist in the pack.

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Team
metadata:
  name: platform-ops
  displayName: Acme Platform Ops Team
spec:
  org: acme
  businessUnit: engineering
  project: platform
  purpose: Operate Acme platform services and reliability.
  roles:
    - sre-platform
  defaultModelProfile: worker-codex
```

## ModelProfile

Intent-level model routing, such as local worker or frontier unblocker. Lives at
`models/<profile-name>.yaml`. Required: `metadata.name`.

```yaml
apiVersion: openagentix.io/v1alpha2
kind: ModelProfile
metadata:
  name: worker-codex
spec:
  provider: openai-codex
  model: gpt-5.4
  intent: Execute known org/project operations with associated role skills.
```

## RuntimeRequirement

Capabilities the runtime should provide or warn about. Lives at
`runtime-requirements/<requirement-name>.yaml`. Required: `metadata.name`.

```yaml
apiVersion: openagentix.io/v1alpha2
kind: RuntimeRequirement
metadata:
  name: shell-readonly
spec:
  capabilities:
    - shell.read
```

See [Runtime Adapters](./adapters) for how a `RuntimeRequirement` maps to an
adapter's native guardrail (or documents the gap when there isn't one).

## Eval

Scenario prompt and success criteria for one skill. Lives at
`evals/<eval-name>.yaml`. Required: `metadata.name`, and `spec.skill` naming an
existing skill in the pack — `aoh validate` rejects an eval with no `spec.skill` or
one pointing at a skill that doesn't exist. Evals gate cheap-model trust per skill.

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Eval
metadata:
  name: platform-sre-basic
spec:
  skill: platform-sre-triage
  prompt: A platform service is unhealthy and Docker disk usage may be high. Triage safely.
```

## Binding

Site-specific association of a role with a target (for example, a `kubeContext` +
default `namespace`). **Lives outside packs**, in a site repository — `Binding` is
deliberately not part of pack layout and loads standalone via `load_binding()`, not
`load_pack()`. Required: `apiVersion: openagentix.io/v1alpha2`, `kind: Binding`,
`metadata.name`, `spec.role`, and a `spec.target` mapping. The referenced role is
checked against the target pack at install time (`aoh install-hermes-agent --binding`).

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Binding
metadata:
  name: kubeops-sresquad
spec:
  role: kubeops-copilot
  target:
    kubeContext: kind-sresquad-demo
    namespace: default
```

For kubernetes targets the Hermes adapter generates a `provision.sh` that creates a
dedicated read-only RBAC identity and a scoped kubeconfig — AOH generates the script,
the operator runs it. The demo `ClusterRole` grants read on everything, including
`Secrets`; production bindings should tighten it. See
[Runtime Adapters](./adapters) for the generated files.

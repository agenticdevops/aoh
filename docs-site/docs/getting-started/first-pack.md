---
title: Your First Pack
---

# Your First Pack

This page validates a real, shipped pack, generates a Hermes-native view of it,
and then scaffolds a brand-new pack from scratch. Run these from the root of the
`aoh` repository.

## Validate a shipped pack

AOH ships a few example packs under `collections/core/`. `kubeops` is a
Kubernetes triage pack with four read-only skills. Validate it:

```bash
uv run aoh validate collections/core/kubeops
```

Expected output:

```text
valid AOH pack: kubeops
```

`validate` checks pack structure and referential integrity — every skill a role
points to exists, every runtime requirement a role references exists, and so on.
If you've used `terraform plan`, this is the same idea: a safe, read-only check
you run before compiling anything, and it's exactly what `adapt-hermes` and the
`install-hermes*` commands run internally before they touch the filesystem.

## Generate a Hermes view

`adapt-hermes` compiles the pack into a Hermes-native directory — files only, no
install into a live Hermes profile:

```bash
uv run aoh adapt-hermes collections/core/kubeops --output /tmp/kubeops-hermes
```

Expected output:

```text
generated 9 Hermes files in /tmp/kubeops-hermes
```

What got generated:

```text
/tmp/kubeops-hermes/
  aoh-hermes.json
  commands/
    ops-k8s-service-health-report.md
    ops-node-notready-triage.md
    ops-pending-pod-triage.md
    ops-pod-crashloop-triage.md
  skills/
    k8s-service-health-report/SKILL.md
    k8s-service-health-report/scripts/collect_health_summary.sh
    node-notready-triage/SKILL.md
    node-notready-triage/scripts/collect_node_diagnostics.sh
    pending-pod-triage/SKILL.md
    pending-pod-triage/scripts/collect_pending_pod_diagnostics.sh
    pod-crashloop-triage/SKILL.md
    pod-crashloop-triage/scripts/collect_pod_crash_diagnostics.sh
```

The mapping:

- Each AOH `skills/<skill>/` copies straight into `skills/<skill>/` — Hermes
  skills are agentskills-format `SKILL.md` files, so nothing needs translating.
- Each skill also gets a generated `commands/ops-<skill>.md` — a Hermes slash
  command that wraps the skill.
- `aoh-hermes.json` is the adapter manifest: which pack this came from, and the
  roles, skills, model profiles, runtime requirements, and evals it saw. Run
  `command cat /tmp/kubeops-hermes/aoh-hermes.json` to see it.

This step only writes files to `--output`. It does not touch `~/.hermes/` or any
live Hermes profile — see [Your First Agent](./first-agent) for the command that
does that.

## Scaffold your own pack

Now create a fresh pack instead of reading an existing one:

```bash
uv run aoh init-pack my-first-pack --output ./my-first-pack --description "demo"
```

Expected output:

```text
created AOH pack: my-first-pack
```

The scaffold:

```text
my-first-pack/
  AOH.yaml
  evals/
    my-first-pack.yaml
  models/
    local-worker.yaml
  roles/
    ops-triage-lead.yaml
  runtime-requirements/
    shell-readonly.yaml
  skills/
    my-first-pack/SKILL.md
```

Note what's absent: there is no `workflows/` directory. AOH does not have a
workflow artifact kind — sequencing across skills is expressed as a **process
skill** (a plain skill whose `SKILL.md` body orchestrates other skills by name).
Everything under `roles/`, `models/`, `evals/`, and `runtime-requirements/` is
optional scaffolding meant to be edited or deleted; only `AOH.yaml` plus one
skill are required for a pack to validate.

Validate what you just scaffolded:

```bash
uv run aoh validate ./my-first-pack
```

```text
valid AOH pack: my-first-pack
```

## Next

[Your First Agent](./first-agent) — turn a pack into a launchable Hermes profile.
See also [Build a Pack](../tutorials/build-a-pack) for a deeper, from-scratch
walkthrough, and [Pack Spec](../reference/pack-spec) for the full artifact
reference.

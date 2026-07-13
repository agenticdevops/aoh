---
name: create-aoh-pack
description: Use when creating or revising reusable Agentic Ops Harness packs, ops skills, workflows, agent roles, model profiles, runtime requirements, evals, or runtime adapter mappings.
---

# Create AOH Pack

## Overview

Create AOH packs as portable "Superpowers for Ops": small, reusable, runtime-adaptable operational capabilities.

## Process

1. Start with one concrete ops use case.
2. Create the starter pack with `aoh init-pack` when available.
3. Define the reusable skill first.
4. Add a workflow that composes the skill with an agent role, model profile, runtime requirements, and evals.
5. Validate the pack with `aoh validate`.
6. Add adapter notes only for runtime-specific mappings.

## Required Pack Shape

```text
pack-name/
  AOH.yaml
  skills/<skill-name>/SKILL.md
  workflows/<workflow-name>.yaml
  agents/<role-name>.yaml
  models/<profile-name>.yaml
  runtime-requirements/<requirement-name>.yaml
  evals/<eval-name>.yaml
```

## Rules

- Keep the pack engine-neutral by default.
- Put runtime-specific details under an adapter or runtime requirement.
- Prefer deterministic scripts for repeatable inspection or transformation.
- Describe risks and required capabilities, but do not claim enforcement unless the target runtime provides it.
- Keep each pack narrow enough to test with one realistic eval.
- Run validation before presenting the pack as usable.

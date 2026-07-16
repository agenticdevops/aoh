---
title: Pack Spec (v1alpha2)
---

# Pack Spec (v1alpha2)

This page mirrors the repository's source of truth,
[`docs/spec.md`](https://github.com/agenticdevops/aoh/blob/main/docs/spec.md). If
this page and `docs/spec.md` ever disagree, `docs/spec.md` wins — file an issue or PR
to reconcile.

AOH packs are engine-neutral operational superpowers. A pack describes what an ops
capability is, how an agent should use it, and what each runtime adapter needs to
materialize.

## Layout

Progressive disclosure: only `AOH.yaml` and at least one skill are required.
Everything else is an opt-in layer for org-scale use.

```text
pack-name/
  AOH.yaml                                      # required
  skills/<skill-name>/SKILL.md                  # required (at least one)
  teams/<team-name>.yaml                        # optional
  roles/<role-name>.yaml                        # optional
  models/<profile-name>.yaml                    # optional
  runtime-requirements/<requirement-name>.yaml  # optional
  evals/<eval-name>.yaml                        # optional
```

:::warning[No `workflows/` or `agents/`]
A `workflows/` or `agents/` directory anywhere in the pack root is a validation
**error**, not a warning — these are stale v1alpha1 layout names. See
[Migration Notes](#migration-notes-v1alpha1--v1alpha2) below.
:::

Bindings (`kind: Binding`) are deliberately **not** part of pack layout — they are
site-specific (role × target) and live in a separate site repository. See
[Artifact Kinds](./artifact-kinds) for the `Binding` schema.

## apiVersion

Every YAML artifact in a pack — `AOH.yaml` and everything under `roles/`, `teams/`,
`models/`, `runtime-requirements/`, `evals/` — must declare:

```yaml
apiVersion: openagentix.io/v1alpha2
```

`openagentix.io/v1alpha1` is rejected outright: `aoh validate` raises an error
pointing at the migration notes. There is no compatibility shim.

## Validation Rules

`aoh validate` checks that:

- `AOH.yaml` uses `apiVersion: openagentix.io/v1alpha2` and `kind: Pack`.
- the pack defines at least one skill; all other artifact kinds are optional.
- every skill has `SKILL.md` frontmatter with matching `name` and a `description`.
- role references point to existing skills, model profiles, and runtime requirements.
- team references point to existing roles and model profiles.
- every eval declares `spec.skill` and it points to an existing skill.
- each YAML artifact has the expected `kind` and `metadata.name`.
- stale v1alpha1 layouts fail loudly: a `workflows/` or `agents/` directory is an
  error.
- bindings load standalone: `apiVersion` v1alpha2, `kind: Binding`, `metadata.name`,
  `spec.role`, and a `spec.target` mapping are required; the referenced role is
  checked against the pack at install time.

Run it against any pack path:

```bash
uv run aoh validate collections/core/docker-disk-cleanup
```

`validate` accepts one pack path at a time.

## Migration Notes (v1alpha1 → v1alpha2)

- `apiVersion`: `openagentix.io/v1alpha1` → `openagentix.io/v1alpha2` in every yaml.
- `kind: Workflow` is gone. Delete single-skill wrapper workflows (the skill already
  covers them). Convert multi-skill workflows into **process skills**: a `SKILL.md`
  that lists the constituent skills in order with any branching/escalation logic,
  added to the owning role's `skills:` list.
- `agents/` → `roles/`; `kind: AgentRole` → `kind: Role`; the role `workflows:` field
  is removed.
- Every `Eval` gains required `spec.skill` naming the skill it tests.
- No compatibility shim and no migrate command — alpha versions carry no compat
  promise.

## Org/Project Role Model

AOH models real operational teams:

- **Org**: company or business unit, such as `acme`.
- **Project**: operational scope, such as `platform` or `ml-platform`.
- **Team**: a group of roles responsible for a project or business unit, such as
  `platform-ops`.
- **Role**: job function within that scope, such as `sre-platform`,
  `devops-automation`, or `mlops-training`.
- **Skills**: capabilities associated with that role, including process skills.
- **Runtime requirements**: tools/capabilities the runtime should provide.

Runtime adapters decide how to map this into their platform. For Hermes, a
role-scoped AOH agent maps to a Hermes profile containing `config.yaml`, `SOUL.md`,
profile-local skills, and a launch script. A team maps to multiple Hermes profiles,
one per role.

## Runtime Boundaries

AOH declares intent and requirements. Runtime adapters map those declarations into
platform-native controls. If a runtime cannot enforce a requirement, the adapter
should warn or document the gap rather than claiming enforcement.

## See also

- [Artifact Kinds](./artifact-kinds) — full schema + minimal yaml example per kind.
- [CLI Reference](./cli) — `validate`, `init-pack`, and the `adapt-hermes` /
  `install-hermes*` commands that run `validate` internally first.
- [Runtime Adapters](./adapters) — how a pack compiles into a runtime profile.

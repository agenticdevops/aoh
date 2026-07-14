# AOH Pack Spec

AOH packs are engine-neutral operational superpowers. A pack describes what an ops capability is, how an agent should use it, and what each runtime adapter needs to materialize.

## Layout

Progressive disclosure: only `AOH.yaml` and at least one skill are required.
Everything else is an opt-in layer for org-scale use.

```text
pack-name/
  AOH.yaml                                      # required
  skills/<skill-name>/SKILL.md                  # required (at least one)
  teams/<team-name>.yaml                        # optional
  workflows/<workflow-name>.yaml                # optional
  agents/<role-name>.yaml                       # optional
  models/<profile-name>.yaml                    # optional
  runtime-requirements/<requirement-name>.yaml  # optional
  evals/<eval-name>.yaml                        # optional
```

## Artifact Kinds

- `Pack`: top-level metadata and ownership.
- `Skill`: agentskills-compatible instructions plus optional scripts/references/assets.
- `Workflow`: composition of skills, agent role, model profile, runtime requirements, and evals.
- `Team`: org/project/BU container that groups related operational roles.
- `AgentRole`: an org/project job function with associated skills, workflows, runtime requirements, model profile, and responsibilities.
- `ModelProfile`: intent-level model routing, such as local worker or frontier unblocker.
- `RuntimeRequirement`: capabilities the runtime should provide or warn about.
- `Eval`: scenario prompt and success criteria for validating future pack behavior.

## Org/Project Role Model

AOH models real operational teams:

- **Org**: company or business unit, such as `acme`.
- **Project**: operational scope, such as `platform` or `ml-platform`.
- **Team**: a group of roles responsible for a project or business unit, such as `platform-ops`.
- **Role**: job function within that scope, such as `sre-platform`, `devops-automation`, or `mlops-training`.
- **Skills**: capabilities associated with that role.
- **Workflows**: repeatable operational flows the role can execute.
- **Runtime requirements**: tools/capabilities the runtime should provide.

Runtime adapters decide how to map this into their platform. For Hermes, a role-scoped AOH agent maps to a Hermes profile containing `config.yaml`, `SOUL.md`, profile-local skills, and a launch script. A team maps to multiple Hermes profiles, one per role.

## Validation Rules

`aoh validate` checks that:

- `AOH.yaml` uses `apiVersion: openagentix.io/v1alpha1` and `kind: Pack`.
- the pack defines at least one skill; all other artifact kinds are optional.
- every skill has `SKILL.md` frontmatter with matching `name` and a `description`.
- workflow references point to existing skills, agent roles, model profiles, runtime requirements, and evals.
- agent role references point to existing skills, workflows, model profiles, and runtime requirements.
- team references point to existing agent roles and model profiles.
- each YAML artifact has the expected `kind` and `metadata.name`.

## Runtime Boundaries

AOH declares intent and requirements. Runtime adapters map those declarations into platform-native controls. If a runtime cannot enforce a requirement, the adapter should warn or document the gap rather than claiming enforcement.

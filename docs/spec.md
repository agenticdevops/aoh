# AOH Pack Spec (v1alpha2)

AOH packs are engine-neutral operational superpowers. A pack describes what an ops capability is, how an agent should use it, and what each runtime adapter needs to materialize.

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

Bindings (`kind: Binding`) are deliberately NOT part of pack layout — they are
site-specific (role × target) and live in a separate site repository. See Artifact
Kinds below.

## Artifact Kinds

- `Pack`: top-level metadata and ownership. `apiVersion: openagentix.io/v1alpha2`.
- `Skill`: agentskills-compatible instructions plus optional scripts/references/assets.
  A **process skill** is a plain skill whose body orchestrates other skills by name
  (order, branching, escalation). No dedicated kind — it is a documented convention.
- `Team`: org/project/BU container that groups related operational roles.
- `Role`: an org/project job function with associated skills, runtime requirements,
  model profile, and responsibilities.
- `ModelProfile`: intent-level model routing, such as local worker or frontier unblocker.
- `RuntimeRequirement`: capabilities the runtime should provide or warn about.
- `Eval`: scenario prompt and success criteria for one skill, referenced by required
  `spec.skill`. Evals gate cheap-model trust per skill.
- `Binding`: site-specific association of a role with a target (e.g.
  `kubeContext` + default `namespace`). Lives outside packs, in a site repo.
  Materialized by adapters at install time (`--binding`); for kubernetes targets
  every runtime adapter (Hermes, Claude Code, Codex) generates a script the operator
  runs, chosen by `spec.access` (default `scoped`; loader rejects any other value):
  - **`scoped`**: `provision.sh` creates a dedicated ServiceAccount bound to an
    explicit get/list/watch RBAC allowlist (never a `*/*` wildcard; Secrets are
    excluded), then writes a scoped `kubeconfig` (0600) next to the script. This is
    a hard enforcement boundary — the cluster API server itself rejects mutations
    from this identity.
  - **`inherit`**: `prepare-overlay.sh` writes NO credentials at all. It resolves
    the target context's cluster/user entry names from the operator's own merged
    kubeconfig (via a redacted `kubectl config view`, never `--raw`), verifies the
    result resolves via `kubectl config view --minify`, and self-checks its own
    output for credential-shaped content before finishing. It writes a minimal
    `kubeconfig-overlay` pinning `current-context` + namespace; the agent then runs
    under the operator's OWN identity, merged in via
    `KUBECONFIG=<overlay>:<original>`. There is NO hard enforcement boundary in this
    mode — whatever the operator's credentials can do, the agent can do.

## Commands

Adapters generate one invokable command per skill, namespaced under the `ops` prefix.
The canonical command name is `ops:<skill>`; each adapter maps the separator to its
runtime's convention:

| Runtime | Surface | Command | Status |
|---|---|---|---|
| Hermes | `commands/ops-<skill>.md` | `ops-<skill>` | shipped |
| Claude Code | `.claude/commands/ops/<skill>.md` (subdir → namespace) | `/ops:<skill>` | shipped |
| Codex | `.agents/skills/ops-<skill>/SKILL.md` (frontmatter `name` rewritten, no separate command file) | `$ops-<skill>` | shipped |
| OpenCode | `command/ops-<skill>.md` | `/ops-<skill>` | planned |

The prefix lives in the spec; separator mapping lives in adapters. Codex has no
custom-prompt surface distinct from skills (project-scoped custom prompts are
deprecated on 0.144.x) — the skill itself, wrapper-named `ops-<skill>`, is both the
capability and the invokable command. See `docs/adapters.md` for the full workspace
layouts, threat model, and guardrail mapping per runtime.

Materialize any of these surfaces with the runtime-neutral CLI entrypoint:
`aoh install --runtime <hermes|claude-code|codex> <pack> --output <dir>
[--binding <file>] [--role <name>] [--profile <name>] [--model <hint>]`. This is the
single call into `ADAPTERS[<runtime>].materialize(...)`; the older `install-hermes*`
subcommands remain as unchanged compat handlers, with `install-hermes-agent` printing
a stderr hint pointing at `aoh install --runtime hermes`.

## Org/Project Role Model

AOH models real operational teams:

- **Org**: company or business unit, such as `acme`.
- **Project**: operational scope, such as `platform` or `ml-platform`.
- **Team**: a group of roles responsible for a project or business unit, such as `platform-ops`.
- **Role**: job function within that scope, such as `sre-platform`, `devops-automation`, or `mlops-training`.
- **Skills**: capabilities associated with that role, including process skills.
- **Runtime requirements**: tools/capabilities the runtime should provide.

Runtime adapters decide how to map this into their platform. For Hermes, a role-scoped AOH agent maps to a Hermes profile containing `config.yaml`, `SOUL.md`, profile-local skills, and a launch script. A team maps to multiple Hermes profiles, one per role.

## Validation Rules

`aoh validate` checks that:

- `AOH.yaml` uses `apiVersion: openagentix.io/v1alpha2` and `kind: Pack`.
- the pack defines at least one skill; all other artifact kinds are optional.
- every skill has `SKILL.md` frontmatter with matching `name` and a `description`.
- role references point to existing skills, model profiles, and runtime requirements.
- team references point to existing roles and model profiles.
- every eval declares `spec.skill` and it points to an existing skill.
- each YAML artifact has the expected `kind` and `metadata.name`.
- stale v1alpha1 layouts fail loudly: a `workflows/` or `agents/` directory is an error.
- bindings load standalone: `apiVersion` v1alpha2, `kind: Binding`, `metadata.name`,
  `spec.role`, and a `spec.target` mapping are required; the referenced role is
  checked against the pack at install time.

## Migration Notes (v1alpha1 → v1alpha2)

- `apiVersion`: `openagentix.io/v1alpha1` → `openagentix.io/v1alpha2` in every yaml.
- `kind: Workflow` is gone. Delete single-skill wrapper workflows (the skill already
  covers them). Convert multi-skill workflows into process skills: a `SKILL.md` that
  lists the constituent skills in order with any branching/escalation logic, added to
  the owning role's `skills:` list.
- `agents/` → `roles/`; `kind: AgentRole` → `kind: Role`; the role `workflows:` field
  is removed.
- Every `Eval` gains required `spec.skill` naming the skill it tests.
- No compatibility shim and no migrate command — alpha versions carry no compat promise.

## Runtime Boundaries

AOH declares intent and requirements. Runtime adapters map those declarations into platform-native controls. If a runtime cannot enforce a requirement, the adapter should warn or document the gap rather than claiming enforcement.

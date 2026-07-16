---
title: Runtime Adapters
---

# Runtime Adapters

An adapter compiles an engine-neutral AOH pack into a runtime-native profile. AOH
never executes anything itself — see [Engine-Neutral by Design](../concepts/engine-neutral)
for the full rule. This page documents what the one adapter that exists today,
Hermes, actually generates, and what's planned for the rest.

:::info[Only Hermes exists today]
Claude Code, Codex, and Goose adapters are **planned**, not built. Everything below
about them is a target shape, not shipped behavior.
:::

## What an adapter does

Given a validated `Pack`, an adapter:

1. Materializes skills into the runtime's skill format.
2. Generates one invokable command per skill under the `ops-<skill>` namespace,
   translated to the runtime's own command convention.
3. Maps `Role` / `Team` structure onto whatever grouping concept the runtime has
   (a Hermes profile, for example).
4. Maps each declared `RuntimeRequirement` onto a native guardrail, or documents
   the gap if the runtime can't enforce it.
5. Writes a manifest describing what it generated, for traceability.

Source: [`src/aoh/adapters/hermes.py`](https://github.com/agenticdevops/aoh/blob/main/src/aoh/adapters/hermes.py),
[`docs/hermes-adapter.md`](https://github.com/agenticdevops/aoh/blob/main/docs/hermes-adapter.md).

## Hermes adapter

The first and, currently, only AOH runtime adapter. It materializes a pack into
Hermes-friendly files without forking Hermes. Four entry points, each backing a CLI
command (see [CLI Reference](./cli) for exact flags):

### `adapt-hermes` — generate files only

```text
hermes-output/
  skills/<skill-name>/SKILL.md
  commands/ops-<skill-name>.md
  aoh-hermes.json
```

Writes files to `--output`; does not touch `~/.hermes/` or any live profile.
`aoh-hermes.json` records the pack name, skills, generated commands, roles, model
profiles, runtime requirements, and evals.

### `install-hermes` — install skills into a live skills directory

```text
~/.hermes/profiles/<profile>/skills/<category>/<skill-name>/SKILL.md
~/.hermes/profiles/<profile>/skills/<category>/<skill-name>/references/aoh-pack.md
~/.hermes/profiles/<profile>/skills/<category>/<pack-name>.aoh-hermes.json
```

Each installed skill also gets a generated `references/aoh-pack.md` describing the
owning pack's roles/models/requirements/evals, so Hermes has that context alongside
the skill.

### `install-hermes-agent` — a launchable custom Hermes profile

```text
<profiles-dir>/<profile>/
  config.yaml       # model/provider/tool settings
  SOUL.md            # AOH role instructions
  skills/            # profile-local AOH skills, scoped to the role if --role given
  aoh-agent.json     # manifest
  launch.sh          # preloads the associated skills, chmod 755
  provision.sh       # only if --binding given, chmod 755
```

`SOUL.md` is generated differently depending on whether `--role` is given: a
role-scoped profile gets the role's purpose, scope, skills, runtime requirements, and
responsibilities; a pack-level profile gets the pack's skills and runtime
requirements directly. If `--binding` is given, `SOUL.md` also gets a `## Binding`
section naming the bound kube context and default namespace, and stating that
mutation attempts are denied by the API server (a denial is the guardrail working,
not an error to work around).

`launch.sh` execs `hermes --profile <profile> --skills <skill,list> chat "$@"`; when
a binding is present it also exports `KUBECONFIG` to the profile-local
`kubeconfig` file that `provision.sh` writes.

### `install-hermes-team` — one profile per team role

Calls `install-hermes-agent` once per role in the team, with profile names
`<profile-prefix>-<role-name>`, then writes a team manifest
`<profile-prefix>-<team-name>.aoh-team.json` listing the generated profiles.

### `provision.sh` for bindings

When `install-hermes-agent` is given `--binding`, it generates (but never runs)
`provision.sh` in the profile directory. Run once, with cluster-admin access, by a
human operator — not AOH:

1. Creates a `ServiceAccount` named `aoh-<binding-name>` in the target namespace.
2. Applies a `ClusterRole` (`aoh-readonly`) granting `get`/`list`/`watch` on `*` and
   a `ClusterRoleBinding` binding it to the service account.
3. Mints a 720h token for the service account and writes a scoped `kubeconfig` next
   to the script (`chmod 600`).

Before rendering any of this, `install_hermes_agent` validates the binding: the role
must exist in the pack, must not conflict with an explicit `--role`,
`target.kubeContext` is required, and `metadata.name` / `target.kubeContext` /
`target.namespace` must all match `^[A-Za-z0-9][A-Za-z0-9._-]*$` — unsafe values are
rejected before they ever reach the generated bash. See
[Artifact Kinds → Binding](./artifact-kinds#binding).

### Mapping summary

- AOH `skills/` copy directly into Hermes-compatible skills, each also getting a
  generated `commands/ops-<skill>.md`.
- AOH `teams/` become groups of role-scoped Hermes profiles.
- AOH `roles/` become role guidance in `SOUL.md` and role-scoped profile skills.
- AOH `models/` are referenced as model intent until deeper Hermes profile
  installation is added.
- AOH `runtime-requirements/` are surfaced as runtime expectations.
- AOH `evals/` are listed in the adapter manifest for future test runners.

### Current scope

The adapter can generate files, install skills into an explicit Hermes skills
directory, create a launchable Hermes profile for a role, or create one profile per
role in a team. It does not switch your sticky Hermes profile, create cron jobs, or
start background services. That keeps v0 safe and fast: AOH can validate and
materialize packs while Hermes remains the runtime.

## RuntimeRequirement → native guardrail mapping

A pack doesn't say "generate an RBAC provisioning script" — it declares a
`RuntimeRequirement` describing the capability it needs (for example,
`kubectl-readonly` or `shell-readonly`). Each adapter maps that declared intent onto
whatever native guardrail its platform actually offers, or documents the gap if it
can't.

Concretely for Hermes: **Hermes has no `kubectl`-aware guardrail.** Its own command
guardrail is a hardcoded pattern list with no `kubectl` subcommand allow/deny
configuration. For a `kubectl-readonly`-style requirement bound to a real cluster,
Hermes does not enforce read-only-ness itself — the generated `provision.sh` and
scoped kubeconfig push enforcement down to **Kubernetes RBAC**: the agent's
`ServiceAccount` can only `get`/`list`/`watch`, so a mutating call is rejected by the
API server regardless of what Hermes would otherwise allow. The adapter is honest
about this gap rather than claiming Hermes enforces something it doesn't. See
[Safe, Read-Only Agents](../concepts/safe-agents) for a worked example, including the
live denial proof.

## The `ops-<skill>` command namespace across runtimes

The canonical command name is `ops:<skill>`; each adapter maps the separator to its
runtime's convention:

| Runtime | Surface | Command |
|---|---|---|
| Hermes | `commands/ops-<skill>.md` | `ops-<skill>` |
| Claude Code | `commands/ops/<skill>.md` (subdir → namespace) | `/ops:<skill>` |
| Codex | `prompts/ops-<skill>.md` | `/ops-<skill>` |
| OpenCode | `command/ops-<skill>.md` | `/ops-<skill>` |

The prefix lives in the spec; separator mapping lives in each adapter.

## Planned adapters

| Runtime | Status |
|---|---|
| Hermes | Built — `src/aoh/adapters/hermes.py` |
| Claude Code | Planned |
| Codex | Planned |
| Goose | Planned |

Runtime-specific knowledge belongs only inside `src/aoh/adapters/<runtime>.py` for
that runtime — the pack spec and `pack.py` model stay engine-neutral so a future
adapter compiles the same pack without the pack author changing a line.

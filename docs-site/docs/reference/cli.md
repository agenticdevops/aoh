---
title: CLI Reference
---

# CLI Reference

Every flag and default below is transcribed directly from the argparse definitions in
[`src/aoh/cli.py`](https://github.com/agenticdevops/aoh/blob/main/src/aoh/cli.py). If
this page and `cli.py` ever disagree, `cli.py` wins.

All commands run through `uv run aoh <command> ...`. Every command that takes a
`pack` argument calls `aoh validate` on it internally before doing anything else, so
a broken pack fails fast.

## `aoh validate`

Validate an AOH pack.

```bash
uv run aoh validate <pack>
```

| Argument | Required | Default |
|---|---|---|
| `pack` (positional, path) | yes | — |

Exit 0 and prints `valid AOH pack: <name>` on success; exit 1 and prints
`invalid AOH pack: <reason>` on a `PackError`. Accepts exactly one pack path — run it
once per pack.

## `aoh init-pack`

Create a starter AOH pack.

```bash
uv run aoh init-pack <name> --output <path> --description <text>
```

| Argument | Required | Default |
|---|---|---|
| `name` (positional) | yes | — |
| `--output` (path) | yes | — |
| `--description` | yes | — |

Prints `created AOH pack: <target>` on success.

## `aoh install`

Install an AOH pack for a runtime — `hermes`, `claude-code`, or `codex`, all
**shipped**. This is the runtime-neutral entrypoint: a thin wrapper around
`ADAPTERS[<runtime>].materialize(request)`.

```bash
uv run aoh install <pack> --runtime <hermes|claude-code|codex> --output <path> \
  [--binding <path>] [--role <name>] [--profile <name>] [--model <hint>]
```

| Argument | Required | Default |
|---|---|---|
| `pack` (positional, path) | yes | — |
| `--runtime` | yes | choices: `hermes`, `claude-code`, `codex` |
| `--output` (path) | yes | — |
| `--binding` (path) | no | `None` |
| `--role` | no | `None` |
| `--profile` | no | `None` |
| `--model` | no | `None` |

Validates the pack first. If `--binding` is given, it is loaded via
`load_binding()` and passed straight through to the adapter — the same binding
validation and safe-value rejection rules described under
`install-hermes-agent` below apply here too, since all three adapters share the
`_k8s.py` rendering helpers. Prints
`installed <runtime> workspace in <output_dir>`, then prints every entry in
`result.diagnostics` to stderr prefixed `warning:` — for example, the Codex
adapter always emits one about its execpolicy rules' bypass gaps, and any
adapter emits one for `access: inherit` bindings (no RBAC boundary). See
[Runtime Adapters](./adapters) for what each runtime generates and the full
threat model.

## `aoh adapt-hermes`

Generate a Hermes-native view of a pack (files only — does not touch
`~/.hermes/`).

```bash
uv run aoh adapt-hermes <pack> --output <path>
```

| Argument | Required | Default |
|---|---|---|
| `pack` (positional, path) | yes | — |
| `--output` (path) | yes | — |

Validates the pack first, then prints `generated <N> Hermes files in <output_dir>`.

## `aoh install-hermes`

Install AOH pack skills into a Hermes skills directory.

```bash
uv run aoh install-hermes <pack> --skills-dir <path> [--category <name>]
```

| Argument | Required | Default |
|---|---|---|
| `pack` (positional, path) | yes | — |
| `--skills-dir` (path) | yes | — |
| `--category` | no | `"aoh"` |

Validates the pack first, then prints `installed <N> Hermes files in <output_dir>`.

## `aoh install-hermes-agent`

Create a launchable Hermes profile for an AOH pack (optionally scoped to one role,
optionally bound to a target via `--binding`).

```bash
uv run aoh install-hermes-agent <pack> \
  [--profiles-dir <path>] --profile <name> \
  [--provider <name>] [--model <name>] [--cwd <path>] \
  [--category <name>] [--role <name>] [--binding <path>]
```

| Argument | Required | Default |
|---|---|---|
| `pack` (positional, path) | yes | — |
| `--profiles-dir` (path) | no | `~/.hermes/profiles` |
| `--profile` | yes | — |
| `--provider` | no | `"openai-codex"` |
| `--model` | no | `"gpt-5.4"` |
| `--cwd` | no | `str(Path.cwd())` (current working directory at invocation) |
| `--category` | no | `"aoh"` |
| `--role` | no | `None` |
| `--binding` (path) | no | `None` |

Validates the pack first. If `--binding` is given, the referenced binding's
`spec.role` must exist in the pack, must not conflict with an explicit `--role`, must
declare `target.kubeContext`, and `metadata.name` / `target.kubeContext` /
`target.namespace` must all match the safe-value pattern `^[A-Za-z0-9][A-Za-z0-9._-]*$`
— unsafe values are rejected before anything is rendered into shell scripts. A
binding also produces a `provision.sh` in the profile directory (see
[Runtime Adapters](./adapters)). Prints `installed Hermes agent profile in
<output_dir>`, then a stderr hint: `hint: prefer 'aoh install --runtime hermes'`.
This command is not deprecated — it still produces a launchable *profile*
(`config.yaml`/`SOUL.md`/`launch.sh`), a different shape than the plain
skills/commands file view `aoh install --runtime hermes` writes — the hint just
points new work at the newer, runtime-neutral entrypoint above.

## `aoh install-hermes-team`

Create Hermes profiles for every role in an AOH team.

```bash
uv run aoh install-hermes-team <pack> \
  [--profiles-dir <path>] --team <name> --profile-prefix <name> \
  [--provider <name>] [--model <name>] [--cwd <path>] [--category <name>]
```

| Argument | Required | Default |
|---|---|---|
| `pack` (positional, path) | yes | — |
| `--profiles-dir` (path) | no | `~/.hermes/profiles` |
| `--team` | yes | — |
| `--profile-prefix` | yes | — |
| `--provider` | no | `"openai-codex"` |
| `--model` | no | `"gpt-5.4"` |
| `--cwd` | no | `str(Path.cwd())` (current working directory at invocation) |
| `--category` | no | `"aoh"` |

Validates the pack first, then creates one profile per role named
`<profile-prefix>-<role-name>`. Prints `installed Hermes team profiles in
<output_dir>`.

## The `ops-<skill>` command namespace

Adapters generate one invokable command per skill, namespaced under the `ops`
prefix. The canonical command name is `ops:<skill>`; each adapter maps the separator
to its runtime's convention:

| Runtime | Surface | Command | Status |
|---|---|---|---|
| Hermes | `commands/ops-<skill>.md` | `ops-<skill>` | shipped |
| Claude Code | `.claude/commands/ops/<skill>.md` (subdir → namespace) | `/ops:<skill>` | shipped |
| Codex | `.agents/skills/ops-<skill>/SKILL.md` (frontmatter `name` rewritten, no separate command file) | `$ops-<skill>` | shipped |
| OpenCode | `command/ops-<skill>.md` | `/ops-<skill>` | planned |

The prefix lives in the spec; separator mapping lives in each adapter. Codex has no
custom-prompt surface distinct from skills (project-scoped custom prompts are
deprecated on 0.144.x) — the skill itself, wrapper-named `ops-<skill>`, is both the
capability and the invokable command. See [Runtime Adapters](./adapters) for what
each adapter actually generates today, including the workspace layouts and the
threat model.

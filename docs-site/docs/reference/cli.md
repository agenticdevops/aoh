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
`ADAPTERS[<runtime>].materialize(request)`, wrapped in turn by the crash-safe
convergent installer (`install_workspace`, see [Site
Reference](./site) → path safety and
[`docs/installs.md`](https://github.com/agenticdevops/aoh/blob/main/docs/installs.md)
for the journal/backup model). `install` has **two mutually exclusive modes**,
enforced by argparse before any pack is loaded: legacy (below) and site fan-out
(further down this section).

### Legacy mode: single pack, single runtime

```bash
uv run aoh install <pack> --runtime <hermes|claude-code|codex> --output <path> \
  [--binding <path>] [--role <name>] [--profile <name>] [--model <hint>] \
  [--discard-local]
```

| Argument | Required | Default |
|---|---|---|
| `pack` (positional, path) | yes | — |
| `--runtime` | yes | choices: `hermes`, `claude-code`, `codex` |
| `--output` (path) | yes | — |
| `--binding` (path) | no | `None` — a **file path** in legacy mode |
| `--role` | no | `None` |
| `--profile` | no | `None` |
| `--model` | no | `None` |
| `--discard-local` | no | `False` — overwrite locally modified owned files instead of refusing to install |

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
threat model. Note the output-nesting asymmetry: the Hermes adapter writes its
profile a level deeper, under `--output/<profile>/`, while the Claude Code and
Codex adapters write their workspace files directly into `--output`. This
mode writes `aoh-manifest.json` into the output directory with
`namingScheme: v1-legacy`. If a previous install's owned files were modified
locally, the install refuses (`install refused: ...`, exit 1) unless
`--discard-local` is passed.

### Site mode: fan out across a fleet

```bash
uv run aoh install --site <dir> \
  [--group <name>] [--binding <name>] \
  [--workspace-root <path>] [--accept-site-root] [--discard-local]
```

| Argument | Required | Default |
|---|---|---|
| `--site` (path) | yes (site mode) | — |
| `--group` | no | `None` — only install bindings in this group |
| `--binding` | no | `None` — a **binding name** in site mode (not a file path); only install this one binding |
| `--workspace-root` (path) | no | see the workspace-root consent chain in [Site Reference](./site) |
| `--accept-site-root` | no | `False` — consent to use the site's advisory `workspaceRoot` |
| `--discard-local` | no | `False` |

Site mode cannot be combined with a positional `pack`, `--runtime`, or `--output`
— argparse rejects the combination outright (`install: --site cannot be combined
with a positional pack, --runtime, or --output`). Requires `site.lock.yaml` to
exist and agree with `site.yaml`'s pack sources; otherwise it errors and names
`aoh lock` as the fix. Installs one workspace per matching binding into
`<effectiveRoot>/<binding-name>/`, each with its own `aoh-manifest.json`
(`namingScheme: v2-site-qualified` — RBAC identities are named
`aoh-<site-name>-<binding-name>`). Per-binding failures (a bad pack reference, a
refused install) are caught, printed (`failed: <binding>: <reason>`), and
isolated — other bindings still install. Prints a per-binding
`installed <binding> (<runtime>) -> <path>` line, then a summary line
(`summary: <N> installed, <M> failed`); exits 1 if any binding failed. See [Site
Reference](./site) for the full precedence and workspace-root consent model.

## `aoh list`

List the fleet workspaces for a site — manifest facts and credential state only
(no local hash checking; that's `aoh status`, planned for v0.3 phase D).

```bash
uv run aoh list [--site <path>] [--workspace-root <path>]
```

| Argument | Required | Default |
|---|---|---|
| `--site` (path) | no | falls back to `UserConfig.site`; errors if neither is set |
| `--workspace-root` (path) | no | `UserConfig.defaults.workspaceRoot` if set, else `~/agents` |

Prints one row per binding in the site: `BINDING`, `ROLE`, `PACK@REF`, `RUNTIME`,
`CONTEXT/NS`, `ACCESS`, `WORKSPACE`, `PROVISIONED`, `CREDENTIAL`.
`PROVISIONED` is `yes` if a `kubeconfig` or `kubeconfig-overlay` file exists in
the workspace; `CREDENTIAL` reads `aoh-provision.json`'s `tokenExpiresAt` and
reports `ok`, `expired`, or `-` if no provisioning has happened yet.

## `aoh config`

Manage the user config at `~/.aoh/config.yaml` (or `$AOH_HOME/config.yaml`).

```bash
uv run aoh config init
uv run aoh config get <dotted.key>
uv run aoh config set <dotted.key> <value>
```

`init` creates a starter file (or ensures `apiVersion`/`kind` are set on an
existing one) and prints `wrote <path>`. `get` prints the value at a dotted key,
or `(unset)` if absent. `set` writes a dotted key (creating intermediate maps as
needed) and prints `set <key> = <value>`. See [Site Reference](./site) for the
full `UserConfig` field reference.

## `aoh lock`

Resolve every pack referenced by a site to a commit and write/update
`site.lock.yaml`.

```bash
uv run aoh lock [--site <path>] [--update [<pack>]] [--yes]
```

| Argument | Required | Default |
|---|---|---|
| `--site` (path) | no | `.` (current directory) |
| `--update` | no | `None` — no value updates every locked pack; a pack name scopes the update to just that pack |
| `--yes` | no | `False` — confirm a source/ref change non-interactively |

Without `--update`, `aoh lock` **initializes only**: it writes entries for packs
that don't have a lock entry yet and never touches an existing one. If
`site.yaml` and an existing lock entry disagree (source, subdir, or ref changed),
it reports the disagreement and refuses, naming the `--update` command that would
resolve it — nothing is silently moved. `--update` re-resolves already-locked
packs; a plain ref move (e.g. `main` advancing) proceeds and prints the old→new
commit, but a **source** change (repo/subdir/ref itself) additionally requires
`--yes`. Prints `wrote <site>/site.lock.yaml` on success. See [Site
Reference](./site) for the full lock model, including why `aoh install --site`
always resolves through the lock rather than `site.yaml`'s ref directly.

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

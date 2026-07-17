---
title: Site Reference
---

# Site Reference

Fields below are taken directly from the loader dataclasses in
[`src/aoh/site.py`](https://github.com/agenticdevops/aoh/blob/main/src/aoh/site.py)
and the CLI wiring in
[`src/aoh/cli.py`](https://github.com/agenticdevops/aoh/blob/main/src/aoh/cli.py).
If this page and the code ever disagree, the code wins.

This is the v0.3 fleet layer: three new kinds — `UserConfig`, `Site`, `SiteLock` —
that sit above individual `Binding` files (see [Bindings as
Inventory](../tutorials/bindings-inventory) for the pack/binding split this builds
on) and let `aoh install --site` fan out across an entire inventory in one command.

## `UserConfig` — the operator's own defaults

Lives at `~/.aoh/config.yaml` (or `$AOH_HOME/config.yaml` if `AOH_HOME` is set),
loaded **lazily** — every command that doesn't need it works fine with no file
present at all (`load_user_config` returns all-defaults). `aoh config init` writes
a starter file.

```yaml
apiVersion: openagentix.io/v1alpha2
kind: UserConfig
packs:
  kubeops: {repo: https://github.com/agenticdevops/aoh, subdir: collections/core/kubeops}
site: /path/to/my-org-site        # or a git URL — used by `aoh list` when --site is omitted
registries: {}                     # named registries — placeholder, v0.3 phase C
defaults:
  runtime: claude-code
  model: gpt-5.4
  workspaceRoot: ~/agents          # OPTIONAL — tri-state, see below
```

| Field | Type | Default when absent |
|---|---|---|
| `packs` | map of name → `PackSource` | `{}` |
| `site` | string (path or URL) | `None` |
| `registries` | map of name → URL | `{}` |
| `defaults.runtime` | string | `"claude-code"` |
| `defaults.model` | string | `None` |
| `defaults.workspaceRoot` | path | `None` (tri-state — see below) |

Manage it with `aoh config init|get|set`:

```bash
uv run aoh config init
uv run aoh config set site /path/to/my-org-site
uv run aoh config get site
uv run aoh config set defaults.runtime claude-code
```

`aoh config get <key>` and `set <key> <value>` take dotted keys, so
`defaults.workspaceRoot` addresses a nested field directly.

## `PackSource` — where a pack comes from

Every `packs:` entry (in `UserConfig` or `Site`) is a `PackSource`, accepted in
YAML as either a structured mapping or a bare string:

```yaml
packs:
  kubeops:
    repo: https://github.com/agenticdevops/aoh
    subdir: collections/core/kubeops
    ref: main                       # defaults to HEAD
  local-pack: /home/me/dev/some-pack   # bare string = local path, no git involved
```

`subdir` is posix-normalized; an absolute subdir or one that escapes the repo root
(`..`) is rejected at load time (`PackError`). Local sources are validated for
symlinks anywhere in the tree at checkout time — the same rule the git export path
enforces (`src/aoh/gitops.py::_validate_local_tree`).

## `Site` — the fleet's shared inventory

`site.yaml` at the root of a site repo, alongside a `bindingsDir` (default
convention: `bindings/`) of individual `Binding` files.

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Site
metadata:
  name: myorg-ops-site
spec:
  workspaceRoot: ~/agents            # ADVISORY ONLY — see workspace-root consent below
  defaults:
    runtime: claude-code
    model: gpt-5.4
  targetDefaults:
    namespace: platform              # merged into every binding's spec.target, lowest precedence
  packs:
    kubeops:
      repo: https://github.com/agenticdevops/aoh
      subdir: collections/core/kubeops
      ref: main
  groups:
    prod:
      vars:
        namespace: platform-prod
  bindingsDir: bindings/
```

| Field | Type | Notes |
|---|---|---|
| `metadata.name` | string | required |
| `spec.workspaceRoot` | path | advisory only, see below |
| `spec.defaults.runtime` / `.model` | string | site-level runtime/model default |
| `spec.targetDefaults` | map | merged under every binding's `spec.target`, **lowest** precedence — kept as a field separate from `defaults` because it's a different concern (target variables, not runtime/model selection) |
| `spec.packs` | map of name → `PackSource` | |
| `spec.groups` | map of name → `{vars: {...}}` | group names validated as safe path segments (lowercase alphanumeric + hyphen) |
| `spec.bindingsDir` | path, relative to the site root | one level deep only, entries sorted, each filename's stem must equal its `metadata.name`, a symlinked directory or a symlinked binding file is rejected, duplicate binding names are rejected |

### `Binding` fields used by a site

A `Binding` loaded as part of a site's `bindingsDir` gains three optional `spec`
fields beyond the standalone `role`/`target` shape (all consumed only in
site context):

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Binding
metadata:
  name: claude-binding
spec:
  role: kubeops-copilot
  pack: kubeops                # which site pack this binding installs
  group: prod                  # merges SiteGroup(prod).vars under target, low precedence
  runtime: claude-code          # overrides site/user runtime default for this binding only
  access: scoped
  target:
    kubeContext: kind-prod-demo
    namespace: default          # highest precedence — wins over group/site target vars
```

`spec.pack` is required only if the site defines more than one pack (a single-pack
site lets every binding omit it — `resolve_binding_settings` falls back to the
sole pack, or raises `PackError` if the site has multiple packs and the binding
doesn't pick one).

### Precedence — three separate chains

Precedence for target variables, runtime, and model are **three distinct chains**,
not one blended fallback — a review finding was that a single merged chain hid
which concern (target vs. runtime vs. model) actually won:

| Concern | Chain (lowest → highest, or CLI-first) |
|---|---|
| target vars | `Site.spec.targetDefaults` → `SiteGroup.vars` → `Binding.spec.target` |
| runtime | CLI flag → `Binding.spec.runtime` → `Site.spec.defaults.runtime` → `UserConfig.defaults.runtime` |
| model | `Site.spec.defaults.model` → `UserConfig.defaults.model` |
| pack | `Binding.spec.pack` → the site's sole pack (if exactly one) → error if ambiguous |

### Workspace-root consent (tri-state)

This is the one place a site file — pulled from a git repo that might not be
yours — could silently redirect writes on your own machine, so the resolution is
deliberately consent-gated, not a plain fallback chain:

```
effective root =
  --workspace-root CLI flag                                   (explicit, always wins)
  > UserConfig.defaults.workspaceRoot   (only if explicitly SET — None is a real, distinct state)
  > Site.spec.workspaceRoot advisory    (used ONLY with --accept-site-root)
  > ~/agents                            (hard default)
```

`UserConfig.defaults.workspaceRoot` is **tri-state**: a config file that doesn't
set it produces `None`, which is treated differently from an explicit value —
"the user has no opinion" falls through to the site advisory (if accepted) or the
default, while an explicit user value always wins over the site's advisory.
Whichever source is used, `aoh install --site` prints a notice to stderr naming
which one won:

```text
workspace root: using default (~/agents = /Users/you/agents)
workspace root: IGNORING site advisory (~/agents) — pass --accept-site-root to use it; falling back to ~/agents
workspace root: using site advisory (~/agents, --accept-site-root)
```

## `SiteLock` — the supply-chain pin

`site.lock.yaml`, committed next to `site.yaml`. This is what makes a fan-out
install reproducible against a specific commit rather than whatever a movable ref
(like `main`) happens to point at right now.

```yaml
apiVersion: openagentix.io/v1alpha2
kind: SiteLock
packs:
  kubeops:
    repo: https://github.com/agenticdevops/aoh
    subdir: collections/core/kubeops
    requestedRef: main
    resolvedCommit: 9750a3cf1e2b...
```

Local-path sources are recorded too, so lock-presence checks stay uniform, but
they're exempt from commit resolution:

```yaml
packs:
  local-pack:
    local: true
    path: /home/me/dev/some-pack
```

### `aoh lock` semantics

```bash
uv run aoh lock --site <dir>                 # initialize: write entries that don't exist yet
uv run aoh lock --site <dir> --update         # move every existing entry to its current ref
uv run aoh lock --site <dir> --update kubeops # move only the `kubeops` entry
uv run aoh lock --site <dir> --update --yes   # confirm a source/ref change non-interactively
```

- **Plain `aoh lock` initializes only.** It writes lock entries for packs that
  don't have one yet. It **never** changes an existing `resolvedCommit` or an
  existing pack's source — if `site.yaml` and the lock disagree on a pack that's
  already locked, `aoh lock` reports it and tells you to pass `--update`.
- **`--update [<pack>]` is the only mover.** Without a pack name, every already-
  locked pack is re-resolved against its current ref. If the move only changes
  the resolved commit (the ref itself, e.g. `main`, moved upstream), it proceeds
  and prints the old→new commit. If the move changes the **source** (repo, subdir,
  or `requestedRef` itself), it additionally requires `--yes` — this is a
  deliberate confirmation gate, since a source change is a bigger trust decision
  than a ref moving forward.

### The lock, not `site.yaml`, decides what installs

`aoh install --site` **requires** a lock that agrees with `site.yaml`:

```text
no site.lock.yaml found at <dir> — run `aoh lock --site <dir>` first
site.yaml and site.lock.yaml disagree on pack `kubeops`'s source/ref — run `aoh lock --site <dir> --update kubeops`
```

Once the lock is present and agrees, every fan-out install resolves each pack
through the lock's `resolvedCommit` — **never** by re-resolving `site.yaml`'s ref
directly. This is proven end-to-end in `tests/test_site_e2e.py`: after locking a
git-sourced `kubeops` pack, a new commit is pushed to the upstream `main` branch,
and re-running `aoh install --site` **without** `aoh lock --update` still installs
the *old* locked commit. Only `aoh lock --update` moves the pin; the next install
then picks up the new commit.

## Path safety

Every name that becomes part of a filesystem path — group names, binding names (via
`bindingsDir` filenames), manifest `ownedFiles`/`artifactMap` entries, journal
`stagingDir`/`backupDir` names — is validated through
[`src/aoh/paths.py`](https://github.com/agenticdevops/aoh/blob/main/src/aoh/paths.py)'s
`safe_segment`/`safe_join` before being joined onto a root directory: no path
separators, no `..`, no absolute segments, and the resolved result must stay under
the root (symlink escapes included). A `Site`'s `bindingsDir` itself is rejected if
it — or any file inside it — is a symlink. See
[`docs/installs.md`](https://github.com/agenticdevops/aoh/blob/main/docs/installs.md)
for how this feeds into the crash-safe install/recovery model, since a manifest or
journal is untrusted input once an install could have written or a human could have
edited it.

## `aoh install --site` end to end

```bash
uv run aoh lock --site examples/sresquad-site
uv run aoh install --site examples/sresquad-site --workspace-root /tmp/fleet
uv run aoh list --site examples/sresquad-site --workspace-root /tmp/fleet
```

Fan-out installs one workspace per binding under
`<effectiveRoot>/<binding-name>/`, each with its own `aoh-manifest.json`. A failure
on one binding (a bad pack reference, a refused install) is caught and reported per
binding — the rest still install, and the command exits 1 only if at least one
binding failed. See [CLI Reference](./cli) for the full flag table.

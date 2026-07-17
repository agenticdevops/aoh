# Crash-Safe Convergent Installs

Every `aoh install` — the legacy single-shot `aoh install --runtime <x> <pack>
--output <dir>` and the v0.3 fan-out `aoh install --site <dir>` — routes through the
same function: `install_workspace()` in `src/aoh/installer.py`. This document
describes what that function actually does, grounded directly in the shipped code
(`src/aoh/installer.py`, `src/aoh/manifest.py`, `src/aoh/paths.py`).

## Why not `copytree`

A naive install that just copies pack files into a workspace directory has two
failure modes at fleet scale:

1. **Accretion.** Re-installing after the pack drops a file leaves the old file
   behind forever — the workspace slowly diverges from what the pack actually
   declares (the "fork problem").
2. **No crash safety.** A kill -9, an OOM, or a power loss mid-copy leaves the
   workspace in an unknown, partially-written state, indistinguishable from a
   successful install unless you inspect every file by hand.

AOH's installer solves both: every install is **convergent** (the workspace ends up
exactly matching what the adapter materialized, stale owned files removed) and
**crash-safe** (an interrupted install always recovers, on the next run, to either
"nothing happened" or "the new install completed" — never a half-written
workspace).

## The manifest: `aoh-manifest.json`

Every successful install writes `aoh-manifest.json` into the workspace root
(`src/aoh/manifest.py::build_manifest`). It records:

- `pack`, `source` (`{repo, subdir, ref}` or `{local: true, path}`),
  `resolvedCommit`, `binding` (name, if any), `runtime`, `adapter`
- `namingScheme` — `v1-legacy` (legacy single-shot installs) or
  `v2-site-qualified` (site fan-out installs, whose RBAC identities are named
  `aoh-<site>-<binding>` instead of the legacy `aoh-<binding>`)
- `ownedFiles` — every file AOH considers itself responsible for in this
  workspace (the manifest file itself included)
- `transformId` — the adapter's canonical→materialized naming transform
  (`identity-v1` for Hermes/Claude Code, `codex-ops-rename-v1` for Codex's
  `ops-`-prefixed skill directories) and `artifactMap` — canonical pack-relative
  path → materialized path, for every file that originated in the pack
- `canonicalHashes` / `materializedHashes` — sha256 (+ executable bit) per file,
  two separate sets so a future capture/drift feature can tell "the pack's own
  content" apart from "what actually landed on disk"

The manifest is written **atomically**: `write_manifest()` writes to a temp file in
the same directory, fsyncs it, then `os.replace()`s it onto the final name — a
crash mid-write leaves either the old manifest or nothing, never a truncated one.

Reading a manifest (`read_manifest()`) validates every `ownedFiles` entry and every
`artifactMap` materialized-side path through `paths.safe_join()` before trusting
it. A manifest can be edited (or, in principle, forged) between installs — treating
it as untrusted input on read is deliberate, not an oversight.

## The install sequence

`install_workspace()` acquires an exclusive, non-blocking `fcntl` lock on
`<workspace-parent>/.aoh-install.lock` before doing anything (held for the whole
critical section, released in `finally`) — a second concurrent `aoh install`
against the same workspace parent fails fast with `InstallRefused` rather than
racing.

1. **Recover first, if needed.** If `.aoh-journal.json` already exists in the
   workspace from a previous, interrupted run, recovery runs before anything
   else — see below.
2. **Refuse on local modification.** The existing manifest's `materializedHashes`
   (if any) are compared against what's actually on disk right now. Any owned file
   that was hand-edited since the last install refuses the whole install
   (`InstallRefused`) unless `--discard-local` is passed. Nothing is touched yet.
3. **Materialize to staging.** The adapter's `materialize()` is called with
   `output_dir` pointed at a staging directory — a **sibling** of the real
   workspace (`<workspace>.parent/.aoh-stage-<txnId>`), same filesystem, so the
   later per-file copy into place is a cheap, same-filesystem rename-class
   operation rather than a cross-device copy.
4. **Write-ahead journal.** `.aoh-journal.json` is written with `phase: "staged"`
   and fsync'd — at this point nothing in the real workspace has been touched, so
   recovering from `staged` is a clean abort (delete staging + journal). The
   journal is then flipped to `phase: "committing"` and fsync'd again — this is
   the durability barrier: once `committing` is on disk, the only safe recovery
   action is to roll forward, never abort, because files may already be partially
   replaced.
5. **Commit.** Per file: back up the old owned file into `.aoh-backup-<txnId>`
   (inside the workspace) before it's overwritten or deleted — this happens
   **always**, not only when `--discard-local` was used — then copy the staged
   file into place (via a temp-name-then-`os.replace()` swap), then remove any
   owned file that's no longer produced by this install (the convergence step).
6. **Finalize.** The real workspace is rehashed, the new manifest is written
   atomically, and the staging dir, backup dir (if empty), and journal are
   deleted last.

## Recovery semantics

The journal (`.aoh-journal.json`) stores `stagingDir` and `backupDir` as
**workspace-relative bare names** (e.g. `.aoh-stage-3f9c…`), never absolute paths
— on recovery they're re-resolved through `paths.safe_join()`, so nothing
path-like from a journal is trusted without validation. It also embeds the
**complete new manifest document** (`newManifest`) at the moment it's written —
roll-forward re-copies files per `newOwned` and then writes that manifest
verbatim; recovery never recomputes what the install was supposed to produce.

| Journal phase found | Recovery action |
|---|---|
| `staged` | Nothing in the real workspace was mutated yet. Delete the staging directory and the journal — clean abort, as if the install never ran. |
| `committing` | Roll **forward**: for every file in `newOwned`, copy from staging into the workspace (backing up any existing file first, unless the backup directory already has content from a prior partial recovery attempt — in which case originals are already preserved and no further backups are taken). Files present in the old manifest but not the new one are removed. The embedded `newManifest` is written. Staging and the journal are deleted. |
| anything else | Recovery refuses and raises loudly — an unrecognized/corrupt journal phase is not guessed at; it's left for a human. |

This means an install interrupted at any point converges to a consistent state on
the very next `aoh install` run against that workspace — no separate `aoh repair`
command, no manual cleanup step, in the common case.

## Owned-file convergence

"Owned" files are exactly the set the adapter materialized this run (recorded in
the manifest's `ownedFiles`). On every install, files that were owned by the
*previous* install but are absent from the *new* one are deleted from the
workspace (after being backed up) — this is what makes re-installing after a pack
drops a file actually remove it, instead of leaving it behind. Files never owned
by AOH (anything a user created in the workspace by hand, outside the manifest)
are never touched.

## Backups

Every replaced or removed owned file is copied into `.aoh-backup-<txnId>` inside
the workspace before it's overwritten or deleted — unconditionally, not only when
`--discard-local` is passed. This means even a plain re-install that replaces
files with new pack content leaves a recovery trail. The backup directory is
removed automatically at the end of a clean install if it ended up empty (nothing
was actually replaced).

## Legacy vs. site-qualified naming

Both install paths write a manifest; they differ only in `namingScheme`:

- **Legacy** (`aoh install --runtime <x> <pack> --output <dir>`,
  `install-hermes-agent`): `namingScheme: v1-legacy`. RBAC identities for
  Kubernetes bindings are named `aoh-<binding-name>`, unchanged from pre-v0.3
  behavior.
- **Site fan-out** (`aoh install --site <dir>`): `namingScheme:
  v2-site-qualified`. RBAC identities are named `aoh-<site-name>-<binding-name>`
  to avoid collisions across sites that happen to reuse a binding name. AOH never
  auto-deletes a superseded legacy-named identity when a binding moves from
  standalone to site-managed — that's a manual cleanup step.

## See also

- `docs/spec.md` — `UserConfig` / `Site` / `SiteLock` kind summaries and the
  source-pinning/lock model this installer's `source`/`resolvedCommit` fields feed
  from.
- `docs-site/docs/reference/site.md` — the docs-site walkthrough of the same
  kinds, precedence rules, and workspace-root consent chain, with a worked
  `site.yaml` example.
- `docs-site/docs/reference/cli.md` — full flag tables for `aoh install --site`,
  `aoh list`, `aoh config`, `aoh lock`.

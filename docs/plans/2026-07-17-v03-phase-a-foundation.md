# v0.3 Phase A — Foundation Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> v2 after codex plan review (REWORK, 14 findings — all folded in; adjudication at bottom).

**Goal:** UserConfig + Site inventory + minimal lock, git source resolution, manifest-backed crash-safe convergent installs (ALL install paths), site-qualified RBAC naming, `aoh install --site` fan-out + `aoh list` + `aoh config` + `aoh lock`.

**Architecture:** Design (authoritative incl. FINAL amendments): `.planning/design/2026-07-17-v03-fleet-lifecycle-design.md`. New: `src/aoh/site.py`, `src/aoh/gitops.py`, `src/aoh/manifest.py`, `src/aoh/installer.py`, `src/aoh/paths.py` (safe-join). Adapter contract standardized: `materialize` writes into EXACTLY `request.output_dir`.

**Tech Stack:** Python 3 + uv, PyYAML, pytest, git CLI (subprocess), hashlib, fcntl.

## Global Constraints

- Tests `rtk proxy uv run pytest -q`; baseline 117 green; NO network in tests (local bare repos); `AOH_HOME` env respected by EVERY command touching `~/.aoh` (config, cache, exports) — tests always set it.
- TDD; engine-neutral (site/gitops/manifest/installer/paths import no adapter/k8s modules; installer takes the adapter as a parameter).
- Design FINAL amendments binding. Plus plan-review rulings: minimal lock in Phase A; every install path manifested; backups ALWAYS on replaced files; consent-able workspace root (tri-state); adapter output contract standardized.
- fcntl discipline everywhere: adjacent `.lock` file, fd held for the whole critical section, `LOCK_EX|LOCK_NB` for refusal paths, release in `finally`; contention tested from a separate process.
- Path safety: all joins through `paths.safe_join(root, *segments)` (resolves, asserts containment, rejects absolute/`..`/empty segments); nothing path-like trusted from manifests/journals without validation.
- Commit trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: paths.py + site.py — UserConfig, Site, extended Binding, precedence

**Files:** Create `src/aoh/paths.py`, `src/aoh/site.py`; Modify `src/aoh/pack.py` (Binding + `pack`/`group`/`runtime` optional str fields, loader reads them); Test `tests/test_site.py`.

**Interfaces (exact — later tasks consume):**
```python
# paths.py
def safe_segment(kind: str, value: str) -> str      # PackError unless ^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$
def safe_join(root: Path, *segments: str) -> Path   # each segment via safe_segment-ish check
                                                    # (no sep, no '..', nonempty); result.resolve()
                                                    # must be under root.resolve(); PackError otherwise

# site.py
@dataclass(frozen=True)
class PackSource:
    repo: str | None; subdir: str = ""; ref: str = "HEAD"; local_path: Path | None = None
def parse_pack_source(value: Any) -> PackSource      # dict{repo,subdir,ref} | str => local path;
                                                     # subdir posix-normalized, absolute/'..' rejected

@dataclass(frozen=True)
class UserConfig:
    packs: dict[str, PackSource]
    site: str | None
    registries: dict[str, str]
    default_runtime: str                  # "claude-code" fallback
    default_model: str | None             # NEW (F7)
    workspace_root: Path | None           # None = NOT SET (F4 — tri-state consent)
def load_user_config(aoh_home: Path | None = None) -> UserConfig   # missing file => all defaults

@dataclass(frozen=True)
class SiteGroup: name: str; vars: dict[str, str]
@dataclass(frozen=True)
class Site:
    root: Path; name: str
    workspace_root_advisory: Path | None
    defaults: dict[str, str]              # runtime/model ONLY (F7)
    target_defaults: dict[str, str]       # NEW separate field (F7): spec.targetDefaults
    packs: dict[str, PackSource]
    groups: dict[str, SiteGroup]
    bindings: list[Binding]
def load_site(root: Path | str) -> Site
# rules: apiVersion/kind strict; bindingsDir one level sorted, filename stem == metadata.name,
# symlinked FILES and symlinked bindingsDir rejected (F8), dup names rejected, unknown group
# rejected, binding.pack must exist, multi-pack + unset binding.pack => PackError

@dataclass(frozen=True)
class ResolvedBinding:
    binding: Binding; pack_name: str; pack_source: PackSource
    runtime: str; model: str | None; target: dict[str, str]
def resolve_binding_settings(site: Site, binding: Binding, user: UserConfig,
                             cli_runtime: str | None = None) -> ResolvedBinding
# precedence (F7, split): target = site.target_defaults < group.vars < binding.target;
# runtime = cli > binding.runtime > site.defaults.runtime > user.default_runtime;
# model = site.defaults.model > user.default_model (binding-scoped only if binding sets it — v0.3: no binding model field, so site>user)
```

- [ ] **RED** `tests/test_site.py` — everything from v1 PLUS (F8 matrix): absolute segment, `a/b` segment, empty, symlinked bindingsDir, uppercase group name rejected; (F7): targetDefaults vs defaults separation asserted, model precedence site>user, runtime cli>binding>site>user; camelCase keys asserted (`workspaceRoot`, `bindingsDir`, `targetDefaults`) (F13); user config absent → `workspace_root is None`; apiVersion/kind wrong → PackError.
- [ ] **GREEN**; suite green. Commit `feat: paths + site inventory — UserConfig, Site, precedence (v0.3 A1)`.

---

### Task 2: gitops.py — mirror cache, safe export, locks

**Files:** Create `src/aoh/gitops.py`; Test `tests/test_gitops.py`.

```python
class GitOpsError(ValueError): ...
def mirror_path(cache_dir, url) -> Path                  # sha256(normalized-url)[:16].git
def ensure_mirror(cache_dir, url) -> Path                # clone --mirror | remote update --prune; adjacent .lock, fd-held, finally-released
def resolve_commit(mirror, ref) -> str
def export_tree(mirror, commit, subdir, dest) -> None
    # (F6) PREFLIGHT: `git ls-tree -r <commit> [<subdir>]` — any mode 120000 (symlink) or
    # 160000 (submodule) => GitOpsError BEFORE extraction; then archive|tar into a PRIVATE
    # temp dir; verify extracted paths stay under it; atomic rename to dest
def source_checkout(source: PackSource, cache_dir) -> tuple[Path, str]
    # local => (path, "local"); git => export to cache_dir/exports/<urlhash>-<commit>-<subdirhash>-v1/
    # (key incl. EXPORT_FORMAT="v1", F6); completion marker file `.complete` written last under the
    # repo lock; existing dir WITHOUT marker => wiped + re-exported; with marker => reused
```

- [ ] **RED** — v1's tests PLUS: submodule-mode entry rejected (fake via `git update-index --cacheinfo 160000`); symlink rejected at PREFLIGHT (assert no partial dest dir left); incomplete export dir (no marker) → re-export; concurrent ensure_mirror from a second *process* (subprocess running a tiny python snippet) blocks/succeeds cleanly (F11); export format key in path.
- [ ] **GREEN**; commit `feat: gitops — mirror cache, preflighted safe export (v0.3 A2)`.

---

### Task 3: adapter output contract + full artifact inventory

(F9 + F5 — prerequisite for the installer, so it precedes it.)

**Files:** Modify `src/aoh/adapters/base.py` (AdapterResult + `artifact_map: dict[str,str]`, `transform_id: str = "identity-v1"`), `hermes.py` (HermesAdapter.materialize writes into EXACTLY request.output_dir — wrapper passes `profiles_dir=output_dir.parent, profile_name=output_dir.name` to the legacy function; legacy CLI paths untouched), `claude_code.py`/`codex.py` (already exact-dir; add inventory); ALL THREE adapters: after materializing, WALK the output dir and return `generated_files` = every regular file created (complete inventory, F5) + artifact_map for pack-sourced files (canonical rel → materialized rel; codex transform id `codex-ops-rename-v1`). Test `tests/test_adapter_contract.py`.

- [ ] **RED**: for each adapter × kubeops+binding: materialize into tmp dir D → every file under D appears in generated_files (walk == set); artifact_map covers every file that originated in the pack (spot: skill scripts, SKILL.md, references) and ONLY those; codex map targets `.agents/skills/ops-*/…` + transform id; hermes materialize output lands in EXACTLY D (no `D/<profile>/` nesting — F9 regression); legacy `install_hermes_agent(profiles_dir=...)` behavior unchanged (existing tests).
- [ ] **GREEN**; suite green (117 + new). Commit `feat: adapter contract — exact output dir + complete artifact inventory (v0.3 A3)`.

---

### Task 4: manifest + crash-safe installer (all install paths)

**Files:** Create `src/aoh/manifest.py`, `src/aoh/installer.py`; Modify `src/aoh/cli.py` (BOTH `install --runtime` legacy single-shot AND future site fan-out route through `install_workspace` — F2; legacy records `namingScheme: "v1-legacy"`); Test `tests/test_installer.py`.

Manifest (as v1 plan) PLUS: `txn` block absent in steady state; every path in ownedFiles/artifactMap validated relative + non-escaping on read (F8).

Installer — journal protocol (F3, exact):
```python
# .aoh-journal.json (written BEFORE any workspace mutation, fsync'd):
# { "txnId": uuid, "phase": "staged",         # staged -> committing -> done(removed)
#   "workspaceRoot": ".", "stagingDir": "<abs>", "backupDir": "<abs .aoh-backup-<txnId>>",
#   "oldOwned": {rel: {sha, exec}}, "newOwned": {rel: {sha, exec}} }
# Sequence under .aoh-install.lock (LOCK_EX|LOCK_NB, fd held, finally-released):
# 0. journal present? -> RECOVER first: phase staged => delete staging+journal (nothing mutated);
#    phase committing => roll FORWARD (re-copy from staging per newOwned, verify hashes, finish)
#    — staging dir is kept until phase done precisely to make roll-forward possible
# 1. verify current owned files vs manifest.materializedHashes;
#    modified & !discard_local -> InstallRefused(files); ALWAYS move replaced/removed owned files
#    into backupDir before overwrite/delete (not only on discard_local)
# 2. adapter.materialize -> stagingDir (same filesystem: workspace.parent/.aoh-stage-<txnId>)
# 3. journal phase=staged -> fsync; flip to committing -> fsync
# 4. per-file: backup old -> copy staged (copy+rename within same fs) -> remove stale owned
# 5. rehash real workspace; write manifest via tmp+rename (atomic, F3); journal phase done => delete journal + staging
```

- [ ] **RED** — v1's cases PLUS: backup dir populated on plain re-install that replaces files (no --discard-local) (F3); recovery both phases (fabricated journals: staged → clean abort; committing → roll-forward completes and hashes verify); manifest write atomicity (tmp file gone after); legacy CLI `aoh install --runtime claude-code … --output D` now produces `D/aoh-manifest.json` with namingScheme v1-legacy (F2) and existing assertions still pass; malicious manifest ownedFiles entry `../x` → refused (F8); lock contention from second process (F11).
- [ ] **GREEN**; commit `feat: manifest + crash-safe convergent installer wired into all installs (v0.3 A4)`.

---

### Task 5: site-qualified RBAC naming

As v1 plan Task 4 PLUS (F12): validate the FINAL rendered `aoh-<site>-<binding>` against the full DNS-1123 regex AND 63-char limit with boundary tests (62/63/64); assert BOTH ServiceAccount and ClusterRoleBinding names; namingScheme in manifest derived from the actual rendered mode (site given or not), asserted both ways.
- [ ] RED/GREEN/commit `feat: site-qualified RBAC identity naming (v0.3 A5)`.

---

### Task 6: minimal site lock + CLI (install --site, list, config, lock)

**Files:** Modify `src/aoh/site.py` (+lock load/write), `src/aoh/cli.py`; Test extend `tests/test_cli.py` + `tests/test_site_lock.py`.

**Minimal lock (F1 — Phase A subset of the design's Phase C semantics):**
```yaml
# site.lock.yaml (committed next to site.yaml)
apiVersion: openagentix.io/v1alpha2
kind: SiteLock
packs:
  kubeops: {repo: …, subdir: …, requestedRef: main, resolvedCommit: <sha>}
```
- `aoh lock [--site …] [--update]`: resolves every site pack ref → commit (gitops), writes lock. Without `--update`, refuses to CHANGE an existing entry whose repo/subdir/requestedRef differ from site.yaml (prints diff, demands --update); local-path sources recorded as `{local: true}` (no commit).
- Fan-out install REQUIRES the lock: missing → error "run `aoh lock` first"; site.yaml/lock disagreement (source or requestedRef) → error; installs check out the LOCK's resolvedCommit, never re-resolve the ref (F1). Local-path sources exempt (used directly).
- CLI structure (F10): `list`/`config`/`lock` subcommands dispatch BEFORE any pack loading; `install` gains mutually exclusive modes — legacy (positional pack + --runtime + --output; --binding = FILE PATH, unchanged) vs site (`--site` present: no positional pack; `--binding` = binding NAME; plus `--group`, `--workspace-root`, `--accept-site-root`, `--discard-local`). argparse enforces exclusivity; all existing CLI tests untouched.
- Effective root (F4): `--workspace-root` > user.workspace_root (when not None) > site advisory IF `--accept-site-root` > `~/agents` default. Advisory used or ignored → one loud notice either way.
- Per-binding failures: catch PackError/GitOpsError/InstallRefused per binding, continue, summarize, exit 1 if any failed (F10).
- `aoh list [--site …]`: `--site` optional — falls back to UserConfig.site (F13); columns per v1 plan (manifest + credential state only).
- `aoh config init|get|set` (AOH_HOME-aware; cache + exports also under AOH_HOME — F13).

- [ ] **RED** — v1's CLI cases PLUS: install without lock → error naming `aoh lock`; lock then install → workspaces materialize at the LOCKED commit (move the fixture branch after locking → re-install still installs old commit — the F1 test); `aoh lock` refusal on changed source without --update; list falls back to configured site; legacy/site mode exclusivity (both positional pack AND --site → argparse error); per-binding failure isolation (one bad binding, other succeeds, exit 1).
- [ ] **GREEN**; suite green; 3 packs validate. Commit `feat: site lock + fan-out install, list, config, lock CLI (v0.3 A6)`.

---

### Task 7: e2e integration (local git only) — live smoke OPTIONAL

As v1 Task 6, amended (F14): the REQUIRED gate is the local bare-repo e2e (git-sourced site, lock, fan-out both runtimes, convergent re-install, moved-branch-changes-nothing-until-lock-update). The kind-cluster provisioning smoke is OPTIONAL — run if the cluster is reachable, record in the task report, but its absence does not fail the task.
- [ ] Commit `test: site fan-out e2e — locked git-sourced packs (v0.3 A7)`.

---

### Task 8: docs + roadmap restructure + field note

As v1 Task 7 PLUS: docs cover `aoh lock` + the lock-required install flow; `docs/reference/site.md` documents tri-state workspace-root consent; the journal/backup behavior documented in docs/adapters.md or a new docs/installs.md.
- [ ] Gates: suite green; docs-site build exit 0; 3 packs validate. Commit `docs: v0.3 phase A shipped — site inventory, lock, convergent installs`.

## Plan-review adjudication (codex, REWORK → v2)

Accepted all 14: F1 minimal lock moved into Phase A (Task 6) with the moved-branch test; F2 all install paths routed through installer (Task 4, v1-legacy scheme); F3 full journal protocol w/ txn phases + always-backup + atomic manifest (Task 4); F4 tri-state workspace_root (Task 1/6); F5 complete artifact inventory via output walk (Task 3); F6 preflight ls-tree + private-tmp atomic export + completion marker + format-versioned key (Task 2); F7 target_defaults/defaults split + user default_model (Task 1); F8 paths.safe_join + adversarial matrix incl. manifest paths (Tasks 1/2/4); F9 adapter exact-output-dir contract + hermes wrapper (Task 3); F10 CLI mode exclusivity + dispatch order + per-binding error isolation (Task 6); F11 fcntl discipline + cross-process tests (Tasks 2/4); F12 full-name DNS validation + both RBAC objects + boundary tests (Task 5); F13 camelCase/apiVersion assertions + AOH_HOME everywhere + list --site optional (Tasks 1/6); F14 live smoke optional (Task 7).

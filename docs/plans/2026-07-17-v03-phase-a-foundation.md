# v0.3 Phase A — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** UserConfig + Site inventory (groups, precedence), git source resolution, manifest-backed crash-safe convergent installs, site-qualified RBAC naming, `aoh install --site` fan-out + `aoh list` + `aoh config`.

**Architecture:** Design (authoritative, incl. FINAL convergence amendments at bottom — they BIND this plan): `.planning/design/2026-07-17-v03-fleet-lifecycle-design.md`. New modules: `src/aoh/site.py` (engine-neutral loaders/precedence), `src/aoh/gitops.py` (ALL git ops; bare-mirror cache; tests use local bare repos only), `src/aoh/manifest.py` + `src/aoh/installer.py` (manifest, crash-safe staged install). Adapters gain artifact-map reporting. CLI grows `install --site`, `list`, `config`.

**Tech Stack:** Python 3 + uv, PyYAML, pytest, git CLI (subprocess), sha256 via hashlib.

## Global Constraints

- Tests: `rtk proxy uv run pytest -q` (exact form). Baseline 117 passing.
- TDD RED→GREEN→commit per task. Engine-neutral: no runtime/k8s concepts in site.py/gitops.py/manifest.py/installer.py (k8s stays in `_k8s.py`, runtimes in adapters).
- NO network in tests — gitops tests build local bare repos in tmp_path (`git init --bare` + a work clone to seed commits).
- Design FINAL amendments are binding: crash-safe staged install (not "atomic swap"); site workspaceRoot needs explicit consent; drift-lite NOT in `aoh list` (manifest + credential state only); SA site-qualified naming lands HERE (Phase A); one group per binding; camelCase YAML keys; UserConfig lazy (every existing command works with no ~/.aoh).
- Path safety everywhere: binding/site/group names = single safe path segments (reuse DNS-1123-ish validation); every output path `resolve()`d and asserted under the effective root; symlinks in bindingsDir rejected.
- All shell interpolation `shlex.quote`; all file writes UTF-8.
- Commit trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- HOME isolation in tests: any code touching `~/.aoh` must accept an explicit base dir (`aoh_home: Path` param defaulting to `Path.home()/".aoh"`); tests pass tmp dirs, never the real home.

---

### Task 1: site.py — UserConfig, Site, extended Binding, precedence

**Files:** Create `src/aoh/site.py`; Modify `src/aoh/pack.py` (Binding + 3 optional fields); Test `tests/test_site.py` (new).

**Interfaces (produced — later tasks consume exactly these):**
```python
# site.py (engine-neutral; imports only pack.py + stdlib + yaml)
@dataclass(frozen=True)
class PackSource:
    repo: str | None          # git URL; None => local_path source
    subdir: str = ""          # normalized, no leading/, no '..'
    ref: str = "HEAD"
    local_path: Path | None = None   # mutually exclusive with repo

@dataclass(frozen=True)
class UserConfig:
    packs: dict[str, PackSource]
    site: str | None
    registries: dict[str, str]        # name -> url (ordered); Phase C consumes
    default_runtime: str              # "claude-code" if unset
    workspace_root: Path              # ~/agents if unset

def load_user_config(aoh_home: Path | None = None) -> UserConfig
    # aoh_home default Path.home()/".aoh"; MISSING FILE => defaults (lazy contract)

@dataclass(frozen=True)
class SiteGroup:
    name: str
    vars: dict[str, str]

@dataclass(frozen=True)
class Site:
    root: Path
    name: str
    workspace_root_advisory: Path | None
    defaults: dict[str, str]          # runtime/model
    packs: dict[str, PackSource]
    groups: dict[str, SiteGroup]
    bindings: list[Binding]           # loaded from bindingsDir

def load_site(root: Path | str) -> Site
def parse_pack_source(value: Any) -> PackSource   # dict form {repo,subdir,ref} or local path str
def validate_path_segment(kind: str, value: str) -> None   # PackError on unsafe
def resolve_binding_settings(site: Site, binding: Binding, user: UserConfig,
                             cli_runtime: str | None = None) -> ResolvedBinding
@dataclass(frozen=True)
class ResolvedBinding:
    binding: Binding
    pack_name: str
    pack_source: PackSource
    runtime: str
    model: str | None
    target: dict[str, str]           # merged: site target defaults < group vars < binding.target
```
- pack.py `Binding` gains `pack: str | None = None`, `group: str | None = None`, `runtime: str | None = None`; `load_binding` reads them (strings, optional); all existing callers unaffected (defaults).
- Site loader rules (design): apiVersion v1alpha2, kind Site; `bindingsDir` one level, sorted order, filename stem MUST equal metadata.name, symlinked files rejected, duplicate names rejected; unknown group in a binding → PackError; binding.pack must exist in site.packs when set; if site has multiple packs and binding.pack unset → PackError (sole-pack default only).
- Precedence exactly per design (split by concern). `parse_pack_source`: dict {repo, subdir, ref} OR plain string = local path; subdir normalized (posix), reject absolute + `..` segments.

- [ ] **Step 1 RED** — `tests/test_site.py` (existing test style: PROJECT_ROOT header, plain assert, try/except PackError; `write()` helper). Tests: user config missing file → defaults (runtime claude-code, workspace_root endswith "agents"); user config parse (packs incl. dict + string local form); site happy path (fixture site: site.yaml + bindings/ with 2 bindings, one grouped); filename≠name rejected; symlink in bindingsDir rejected; duplicate binding names rejected; unknown group rejected; multiple-packs + unset binding.pack rejected; precedence: target merge order (site defaults < group vars < binding.target keys win), runtime binding>site>user, pack resolution; `validate_path_segment("binding", "../x")` rejected, "ok-name" accepted; Binding new fields loaded + defaulted.
- [ ] **Step 2 GREEN** — implement; suite green (expect ~117+12).
- [ ] **Step 3** — commit `feat: site inventory — UserConfig, Site, groups, precedence (v0.3 A1)`.

---

### Task 2: gitops.py — mirror cache, locks, resolve, export

**Files:** Create `src/aoh/gitops.py`; Test `tests/test_gitops.py`.

**Interfaces:**
```python
class GitOpsError(ValueError): ...

def mirror_path(cache_dir: Path, url: str) -> Path        # cache_dir/<sha256(normalized url)[:16]>.git
def ensure_mirror(cache_dir: Path, url: str) -> Path      # clone --mirror | remote update --prune; per-repo .lock file (fcntl)
def resolve_commit(mirror: Path, ref: str) -> str         # rev-parse <ref>^{commit}; GitOpsError w/ ref name on failure
def export_tree(mirror: Path, commit: str, subdir: str, dest: Path) -> None
    # git -C mirror archive <commit> [<subdir>] | tar -x into dest (strip subdir components);
    # rejects: subdir missing at commit; any symlink in the exported tree (post-extract scan → GitOpsError)
def source_checkout(source: PackSource, cache_dir: Path) -> tuple[Path, str]
    # local_path → (path, "local"); git → ensure_mirror+resolve+export to cache_dir/exports/<hash>-<commit>/ (memoized), returns (pack_root, commit)
```
All subprocess `git` invocations `check=True`, captured output in errors. No writes to any remote in this task (write-ops = Phase B).

- [ ] **Step 1 RED** — tests build a local fixture: `git init --bare origin.git`; seed via temp clone with a minimal valid pack under `collections/demo/` committed + tagged `v1`; then: ensure_mirror creates mirror + is idempotent; resolve_commit("v1") == resolve_commit of the tag's commit; export_tree extracts only the subdir (AOH.yaml at dest root); missing subdir → GitOpsError; symlink committed into repo → export rejected; source_checkout local passthrough; source_checkout git returns valid loadable pack (`load_pack` on it) + commit; second call memoized (same path, no re-export — assert mtime unchanged).
- [ ] **Step 2 GREEN**; suite green. **Step 3** commit `feat: gitops — bare-mirror cache, resolve, safe subtree export (v0.3 A2)`.

---

### Task 3: manifest + crash-safe convergent installer

**Files:** Create `src/aoh/manifest.py`, `src/aoh/installer.py`; Modify `src/aoh/adapters/base.py` (+`artifact_map`, `transform_id` on AdapterResult), `src/aoh/adapters/{hermes,claude_code,codex}.py` (populate them); Test `tests/test_installer.py`.

**Interfaces:**
```python
# base.py additions (defaulted — existing constructors unaffected)
@dataclass(frozen=True)
class AdapterResult:
    ...existing...
    artifact_map: dict[str, str] = field(default_factory=dict)  # canonical rel path -> materialized rel path
    transform_id: str = "identity-v1"                           # codex: "codex-ops-rename-v1"

# manifest.py
MANIFEST_NAME = "aoh-manifest.json"
NAMING_SCHEME = "v2-site-qualified"   # standalone installs record "v1-legacy"
def build_manifest(*, pack, source: PackSource, commit: str | None, result: AdapterResult,
                   binding, runtime: str, naming_scheme: str) -> dict
    # includes: pack, source{repo,subdir,ref}, resolvedCommit, binding, runtime, adapter,
    # namingScheme, generatedAt(iso), ownedFiles[rel], transformId, artifactMap,
    # canonicalHashes{skill: {tree: sha, files: {rel: {sha, mode}}}}, materializedHashes{same shape}
def write_manifest(workspace: Path, doc: dict) -> None
def read_manifest(workspace: Path) -> dict | None
def hash_tree(root: Path) -> dict     # {tree: sha256, files: {rel: {sha, exec: bool}}}

# installer.py — crash-safe staged install (design FINAL amendment wording)
class InstallRefused(ValueError): ...
def install_workspace(*, adapter, request, source: PackSource, commit: str | None,
                      naming_scheme: str, discard_local: bool = False) -> AdapterResult
    # 1. workspace lock file (.aoh-install.lock, fcntl; InstallRefused if held)
    # 2. if manifest exists: verify owned materialized files vs manifest hashes;
    #    modified & not discard_local -> InstallRefused (lists files); discard_local -> backup dir .aoh-backup-<ts>/
    # 3. adapter.materialize into STAGING dir (same filesystem: workspace.parent/.aoh-stage-<pid>/)
    # 4. write journal .aoh-journal.json (old owned files, new owned files) in workspace
    # 5. per-file replace: copy staged owned files over, remove stale owned files absent from new set
    #    (unowned files NEVER touched); fsync-ish best effort
    # 6. recompute materialized hashes from the real workspace; write manifest; remove journal; release lock
    # recovery: if journal present at start -> finish or roll back per journal before proceeding
```
- Adapters: hermes/claude_code populate identity artifact_map (skill → same rel path under their skills dir); codex maps `skills/<s>/…` → `.agents/skills/ops-<s>/…` with `transform_id="codex-ops-rename-v1"`.

- [ ] **Step 1 RED** — tests (tmp workspaces, claude-code adapter as the vehicle, kubeops pack): fresh install writes manifest w/ owned files + both hash sets + artifact_map; re-install identical = no-op-ish (manifest regenerated, files same); pack changes (mutate a copy of the pack) → re-install updates + REMOVES stale owned file (add then remove a skill); local modification of an owned file → InstallRefused naming it; `discard_local=True` → proceeds + backup dir contains the old file; unowned file (user's notes.txt in workspace) survives every re-install; simulated crash: pre-place a journal describing a half-done state → install first recovers; codex artifact_map has ops- mapping + transform id; lock contention: second install with lock held → InstallRefused.
- [ ] **Step 2 GREEN**; suite green. **Step 3** commit `feat: manifest + crash-safe convergent installer (v0.3 A3)`.

---

### Task 4: site-qualified RBAC naming

**Files:** Modify `src/aoh/adapters/_k8s.py` (`render_provision_script(binding, site_name: str | None = None)` — SA name `aoh-<site>-<binding>` when site_name else legacy `aoh-<binding>`; ClusterRoleBinding follows; validate combined length ≤ 63 chars DNS label, PackError otherwise), `src/aoh/adapters/*` (pass-through param via MaterializeRequest.options["site_name"]), `src/aoh/manifest.py` naming scheme recorded (already wired T3); Test extend `tests/test_adapter_base.py`.

- [ ] **Step 1 RED**: provision with site → `SA_NAME='aoh-myorg-ops-site-kubeops-sresquad'`-style (site-qualified), without site → legacy name unchanged (regression); >63 char combination → PackError; manifest records the right namingScheme per mode.
- [ ] **Step 2 GREEN**; suite green (all 117 legacy tests untouched — legacy default). **Step 3** commit `feat: site-qualified RBAC identity naming (v0.3 A4)`.

---

### Task 5: CLI — install --site fan-out, list, config

**Files:** Modify `src/aoh/cli.py`; Test extend `tests/test_cli.py` (+ site fixture helper).

- `aoh install --site <path> [--group g] [--binding name] [--accept-site-root] [--discard-local]`
  (site path only in v0.3 — git site URL later). Effective root: `--workspace-root` flag > UserConfig > (site advisory ONLY with `--accept-site-root`, printed loudly) > `~/agents`. For each selected ResolvedBinding: source_checkout → load_pack → validate → install_workspace via ADAPTERS[runtime] → print result line + diagnostics to stderr. Per-binding failure doesn't abort the rest (collected, exit 1 if any failed).
- `aoh list --site <path>`: table columns binding | role | pack@ref | runtime | context/ns | access | workspace | provisioned (kubeconfig or overlay present) | credential state (aoh-provision.json expiry: ok/expired/–). NO local hash checks (design: drift-lite dropped).
- `aoh config init|get <key>|set <key> <value>` on ~/.aoh/config.yaml (respect `AOH_HOME` env for tests).
- Keep every existing command working with zero config present (lazy contract).

- [ ] **Step 1 RED** — CLI tests with a tmp site fixture (site.yaml + 2 bindings, one codex one claude-code via binding.runtime, local-path pack source pointing at collections/core/kubeops): fan-out creates both workspaces under tmp root (passed via --workspace-root); manifests present; --group filters; --binding filters; list prints both rows incl. runtime + access; site advisory root WITHOUT --accept-site-root ignored (uses default/flag) + notice printed; config init creates file (AOH_HOME=tmp), set/get roundtrip; second install run converges (no error, stale-free).
- [ ] **Step 2 GREEN**; suite green; 3 packs validate. **Step 3** commit `feat: aoh install --site fan-out, aoh list, aoh config (v0.3 A5)`.

---

### Task 6: integration proof — git-sourced site end-to-end

**Files:** Test `tests/test_site_e2e.py`; evidence appended to `docs/demos/` only if live bits run.

- [ ] **Step 1** — e2e test (still local-only): build a bare git repo fixture containing the kubeops pack under `collections/core/kubeops` (copy from repo, commit, tag v1); site.yaml pins {repo: file://…, subdir…, ref: v1}; fan-out install of 2 bindings; assert: workspaces materialized, manifest resolvedCommit == tag commit, re-install after committing a pack change to the fixture repo + moving the tag → with ref still v1-old-commit? (v1 immutable here) → use ref: main to show BEHIND-precursor: manifest commit updates on re-install. Codex + claude-code both exercised.
- [ ] **Step 2** — live smoke (this machine, consented): `uv run aoh install --site <tmp site pointing at the real repo path> --workspace-root /private/tmp/claude-501/a6-fleet` for 2 bindings incl. the real sresquad binding (scoped); run one provision.sh against kind-sresquad-demo → confirm site-qualified SA name created (`kubectl get sa` shows `aoh-<site>-kubeops-sresquad`); `aoh list` shows provisioned + credential ok. Keep evidence in the task report (formal evidence doc = Phase D validation ritual).
- [ ] **Step 3** — suite green; commit `test: site fan-out e2e — git-sourced pack, convergent reinstall (v0.3 A6)`.

---

### Task 7: docs + roadmap restructure + field note

**Files:** Modify `.planning/ROADMAP.md` (close v0.2 with a pointer; new v0.3 table A–E per design; parking → v0.4), `.planning/STATE.md` (position: v0.3 phase A done; dated log entry, additions only), `.planning/PROJECT.md` (decision rows: workspace-root ownership; crash-safe convergent install; site-qualified naming; structured PackSource), `CHANGELOG.md` (Added: site inventory, fan-out, list, config, manifest, crash-safe installs, site-qualified RBAC names; Changed note re naming scheme for site installs), `docs/spec.md` (new kinds UserConfig/Site summary + Binding's 3 new optional fields), `docs-site`: reference page `docs/reference/site.md` (schemas + precedence + safety rules, grounded in site.py), tutorial update `tutorials/bindings-inventory.mdx` (real site.yaml now — replace the hypothetical framing), field note `blog/2026-07-17-fleet-inventory.md` (first-person, concise, truncate, tags [fleet, ansible]; "inventory, the ansible idea AOH needed"), sidebar entry.
- [ ] Build gates: `rtk proxy uv run pytest -q` green; `npm --prefix docs-site run build` exit 0; 3 packs validate. Commit `docs: v0.3 phase A — site inventory shipped (roadmap restructure, site reference, field note)`.

## Self-review notes

- Design-FINAL amendments all mapped: consent flag (T5), crash-safe wording + journal/backup/lock/unowned-preservation (T3), drift-lite absent from list (T5), SA naming in A w/ legacy preserved + scheme recorded (T4), one group (T1), camelCase (T1 schemas), lazy config (T1/T5).
- Engine-neutral held: site.py/gitops.py/manifest.py/installer.py import no adapter/k8s modules (installer takes adapter as a parameter).
- Phase B consumes gitops (write ops added there); Phase C consumes PackSource+registries field; Phase D consumes manifest hash sets + journal machinery; Phase E consumes site + provisioned identities. No forward dependency violated.
- Test count math approximate; every task's gate = suite green.

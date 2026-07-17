# v0.3 — Fleet Lifecycle: Milestone Design v2

Date: 2026-07-17. v1 reworked after external review (codex gpt-5.6-sol, verdict REWORK,
12 findings — all adjudicated; see "Review adjudication" at bottom). Status: v2 pending
convergence review.

## Vision (unchanged)

draft skill locally → use immediately → promote to pack repo (git = truth) → publish
(registry index) → pin + lock (site repo) → materialize fleet (adapters) → operate
in-session (console) → improve → capture back → loop. Ansible frame: role⇄skill,
collection⇄pack, inventory⇄site, galaxy⇄registry, control node⇄console,
ad-hoc→role ⇄ draft→promote. AOH never executes; no templating engine.

## Roadmap restructure

- v0.2 closes (phases 1, 2, 2.5, 3, 5 done). Phases 4/7/8 fold into v0.3. Eval runner → v0.4.
- v0.3 phases: **A foundation (now incl. minimal manifest + convergent install) →
  B authoring/promote → C registry+lock → D drift status/sync/capture →
  E console (claude-code, scoped-only)**. Registry search + public discovery, Codex
  console, inherit-mode console → v0.4.

## Decisions (v2; ► = changed by review)

| Decision | Choice | Why |
|---|---|---|
| Sequencing | A→B→C→D→E | ► A now carries the drift-manifest foundation — our own decision "drift before installs multiply" (PROJECT.md 2026-07-14) demands it precede fan-out |
| Promote flow | Direct commit default, `--pr` opt-in | user decision; ► hardened git semantics below |
| Registry home | `agenticdevops/aoh-registry`; orgs mirror privately | ► named registries + integrity lock; search/public discovery deferred |
| User config | `~/.aoh/config.yaml`, cache `~/.aoh/repos/` (0700) | ► loaded lazily — all existing commands work without it |
| Skills born local | runtime-native local dirs are the draft area | unchanged |
| cwd stability | names in commands, locations in config, git in cache | unchanged |
| ► Workspace root ownership | Effective root = CLI flag > UserConfig > default `~/agents`. Site's `workspaceRoot` is ADVISORY (used only if user config silent, and printed loudly) | a remote site file must not direct writes on the operator's machine |
| ► Path safety | Binding/group/site names validated as single safe path segments in the loader; every output path resolved + asserted under the root; symlinks in bindings dirs rejected; nothing path-like trusted from workspace-editable manifests | fan-out = filesystem writes driven by remote data |
| ► Structured pack source | `{repo: <git-url>, subdir: <rel-path>, ref: <ref>}` replaces `//subdir` strings (accepted in yaml as either; normalized internally; subdir normalized, no `..`/absolute, symlink-escape rejected; local dirs distinguished from git sources — only git sources support drift/promote) | `//` is URL-ambiguous |
| ► Convergent install | Materialization = atomic staging (build to temp, swap), owned-file tracking in the manifest, stale owned files removed on re-install; local modifications detected and install refuses (pre-drift, `--discard-local` to override) | copytree accretion = the fork problem at fleet scale |
| ► Capture reversibility | Manifest records canonical→materialized mapping per artifact + adapter transform id (e.g. codex `ops-` rename); capture inverse-transforms and validates the resulting pack before commit; runtime-generated files (AGENTS.md, config, rules, settings, hooks) never captured | codex rename would corrupt packs |
| ► Git cache discipline | Bare mirror clones keyed by normalized URL hash; per-repo lock file; every write op uses a fresh temp worktree from freshly-fetched origin default branch; fetch again before push; fast-forward pushes only; same-skill upstream change since promotion base → abort with `--pr` suggestion; identical re-promote = successful no-op printing existing sha; `user.name`/`user.email` verified before commit | mutable pull-cache races + non-FF hazards |
| ► Registry integrity | Index versions = `{ref, commit}` (+ optional `treeSha256`); site repo gains **`site.lock.yaml`**: registry name, normalized source, subdir, requested ref, resolved commit, pack tree sha256. Installs resolve through the lock; `aoh lock --update` moves it. Mutable refs (`main`) legal but called *tracking refs*, resolved into the lock, movable only by explicit lock update | tags move; branches are mutable; pin ≠ ref |
| ► Registry trust | Registries are NAMED in UserConfig (`registries: {myorg: url, public: url}` ordered); site pins may say `registry: myorg`; "not found" ≠ "unavailable/unauthorized" — NEVER fall through to a public registry on auth/network failure; chosen registry+source+commit recorded in lock and displayed | dependency confusion |
| ► Groups | One group per binding in v0.3 (`spec.group`, optional) | merge-order complexity deferred |
| ► Precedence (split by concern) | target vars: site target defaults → group vars → binding.target. runtime: binding → site default → user default. model: site → user (binding override only if explicitly set). pack: binding.pack → site sole-pack default → error if ambiguous | one blended chain hid distinct concerns |
| ► Console scope | v0.3 console = Claude Code runtime, `access: scoped` bindings ONLY (inherit bindings rejected with a clear error); Codex console deferred (its skills aren't identity boundaries; `.codex/agents/*.toml` custom agents are the right primitive to evaluate in v0.4) | identity + credential-concentration honesty |
| ► Secrets language | "AOH does not intentionally manage secrets." Promote/capture copy only regular files under the skill root; reject `.git`, symlinks, devices, sockets, path escapes, oversized files; staged diff shown before direct push; optional secret-scan hook, never claimed complete | old claim unsupportable |
| ► Schema naming | camelCase in YAML (`workspaceRoot`, `siteLock`) matching existing AOH kinds; apiVersion stays v1alpha2 (new kinds + optional fields; strict validation per kind) | consistency |

## Phase A — Foundation: config, site, convergent fan-out, list

### ~/.aoh/config.yaml (kind: UserConfig, lazy-loaded)
```yaml
apiVersion: openagentix.io/v1alpha2
kind: UserConfig
packs:
  kubeops: {repo: https://github.com/agenticdevops/aoh, subdir: collections/core/kubeops}
  myorg-ops: {repo: git@github.com:myorg/ops-pack.git}
site: git@github.com:myorg/ops-site.git       # or local path
registries: {}                                 # named, Phase C
defaults: {runtime: claude-code, workspaceRoot: ~/agents}
```

### site.yaml (kind: Site)
```yaml
apiVersion: openagentix.io/v1alpha2
kind: Site
metadata: {name: myorg-ops-site}
spec:
  workspaceRoot: ~/agents           # ADVISORY; CLI/UserConfig override, use is printed
  defaults: {runtime: claude-code, model: gpt-5.4}
  packs:
    kubeops: {repo: https://github.com/agenticdevops/aoh, subdir: collections/core/kubeops, ref: main}
  groups:
    prod: {vars: {namespace: platform}}
  bindingsDir: bindings/            # one level, deterministic order, unique names,
                                    # filename must equal metadata.name, symlinks rejected
```
Binding optional spec fields (all three, defaulted): `pack`, `group` (single), `runtime`.
Loader keeps standalone bindings working unchanged.

### Convergent materialization (the drift foundation, moved here from old Phase D)
- Every install writes `aoh-manifest.json`: pack name, source {repo, subdir}, resolved
  commit, per-skill tree hash + per-file hashes (incl. exec bit), canonical→materialized
  artifact map + transform id, owned-file list, binding, adapter, runtime, timestamp.
  Two hash sets: canonical-source hashes AND materialized-runtime hashes.
- Install = stage to temp dir → atomic swap; removes stale owned files; refuses when
  owned files were locally modified (`--discard-local` overrides, after backup).
- `aoh install --site … [--group g] [--binding b]` fan-out; per-binding result +
  diagnostics; workspace path = `<effectiveRoot>/<binding-name>/` (validated segment).
- `aoh list [--site …]`: binding, role, pack@resolvedRef, runtime, cluster/ns, access,
  path, provisioned?, drift-lite (manifest vs workspace quick check).

## Phase B — Authoring: draft local, promote central

- Authoring skill pack `collections/core/aoh-authoring` (drafting guidance + validate +
  promote invocation), installable user-globally.
- `aoh skill promote <name> [--from dir] --pack <name> [--pr]`
  - source discovery upward from cwd (`.claude/skills`, `.agents/skills`); validates
    skill standalone; copy hygiene per Secrets decision (regular files only, size caps).
  - git flow per Git-cache-discipline decision (bare mirror + lock + temp worktree +
    FF-only + same-skill-conflict abort→`--pr`). Direct default; `--pr` = branch +
    `gh pr create`.
  - Full pack validation runs in the worktree BEFORE commit; staged diff printed.
  - No-op re-promote exits 0 with existing sha.

## Phase C — Registry + lock

- `aoh-registry` repo, `index.yaml`: kind Registry, packs → {source {repo, subdir},
  description, versions: [{ref, commit}]}. Registry PR checklist verifies tag/commit
  agreement + pack validation (manual process documented; tooling later).
- UserConfig `registries:` named + ordered; site pins may name a registry; resolution:
  explicit source > named registry; hard distinction between not-found and
  unavailable/unauthorized (no public fallback on the latter); conflicts warned.
- `site.lock.yaml` (committed): per pack — registry name, source, subdir, requested
  ref, resolved commit, treeSha256. `aoh lock [--update]`. Installs/sync resolve via
  lock; tag-moved-vs-lock = hard error.
- `aoh install kubeops@v0.2.0 --runtime …` (standalone, lockless) still works.

## Phase D — Drift: status, sync, capture

- Five-state compare per skill (B=installed base from manifest, D=desired at locked
  ref, W=canonicalized workspace content): CURRENT (W=B=D) / BEHIND (W=B≠D) /
  MODIFIED (W≠B=D) / CONVERGED (W=D≠B → refresh manifest) / DIVERGED (all differ →
  file-level three-way merge attempt, else conflict). Content hashes decide — a moved
  repo sha alone with unchanged skill subtree ≠ BEHIND.
- `aoh status [--site]` per-workspace, per-skill table.
- `aoh sync [--site --group]`: auto-updates only clean BEHIND; DIVERGED/MODIFIED need
  `--discard-local` (backup first, confirm) or capture-then-sync.
- `aoh capture <binding> [--skill name] [--pr]`: inverse-transform via manifest map,
  validate canonical pack in worktree, then promote machinery. Capture with a
  tag-locked pack targets the repo's default/contribution branch (never mutates tags).
  Runtime-generated files never captured.

## Phase E — Fleet console (claude-code, scoped-only)

- `aoh console --site … [--group g] --output <dir>`: generates (never executes):
  - `provision-all.sh` — plan-style: lists targets, per-target confirm (or `--yes`),
    continues/stops policy explicit; runs each binding's provisioning
  - `kubeconfigs/<binding>.yaml` slots (0600; console root 0700), expiry surfaced from
    aoh-provision.json (+ refresh = re-run provisioning)
  - `.claude/agents/<binding>.md` — concise subagent per binding pinning its
    kubeconfig path; honest note: instructions do NOT enforce credential selection
  - fleet skill (name→identity map) + generalized fail-closed kubectl-guard: read verbs
    AND `--kubeconfig` value ∈ fleet identity paths
  - CLAUDE.md = rendered inventory
- `access: inherit` bindings are REJECTED for console inclusion (clear error).
- Threat language: per-identity RBAC boundaries; audit distinguishes credentials, not
  subagent intent; console = credential concentration point — root perms + expiry
  surfaced; guardrail ≠ boundary, as always.
- SA/ClusterRoleBinding names become site-qualified (`aoh-<site>-<binding>`) to avoid
  cross-site collisions (provisioning change, Phase A or E — decide at plan time).

## Cross-cutting

- Docs per phase (site tutorials/reference + field note each; ansible table grows).
- Tests TDD; loaders engine-neutral in pack.py (or a new `site.py`); ALL git ops in
  `src/aoh/gitops.py`, tested against local bare repos only.
- Out of scope v0.3: eval runner, hosted registry, `aoh search`/public discovery,
  pack deps, Goose, Codex/inherit console, multi-group bindings, multi-user locking.

## Open questions (v2)

- site-qualified SA names: rollout implication — re-provision renames identities;
  do it in Phase A (before fleets exist) or Phase E?
- `aoh list` drift-lite in Phase A vs full status only in D — keep or drop the lite?

## Review adjudication (codex gpt-5.6-sol round 1: REWORK, 12 findings)

Accepted in full: F1 (workspace-root ownership + path containment), F2 (transform map +
inverse-transform capture), F3 (five-state drift + --discard-local + tag-capture
branch rule), F4 (manifest/convergence moved into Phase A — matches our own 2026-07-14
drift-first decision), F5 (bare-mirror cache + locks + temp worktrees + FF-only),
F6 (lockfile + {ref, commit} versions), F7 (named registries, no fallback on auth
failure), F9 (console hardening: 0700/0600, expiry, plan-style provision-all,
generate-never-execute), F10 (three fields, split precedence, one group, camelCase,
lazy UserConfig), F11 (structured source), F12 (secrets language + copy hygiene).
Accepted-adapted: F8 + cut recommendation — console NOT cut (explicit user
requirement: in-session fleet operation) but reduced to claude-code scoped-only and
sequenced last; Codex console deferred to v0.4 pending `.codex/agents/*.toml`
evaluation. Registry search/public discovery cut from v0.3 per recommendation;
minimal named-registry + lock retained (C).
Open questions from v1: answered per review (bindings dir yes with constraints;
`main` = tracking ref resolved into lock; console context manageable but identity
risks are the real issue — addressed; hashes = per-skill tree + per-file + dual
canonical/materialized sets).

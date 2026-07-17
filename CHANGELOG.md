# Changelog

All notable changes to AOH. Format: [Keep a Changelog](https://keepachangelog.com/),
versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added

- **v0.3 phase A — fleet inventory, lock, convergent installs** (SDD, commits
  `9750a3c`→`3e657df`, 307 tests):
  - `kind: UserConfig` (`~/.aoh/config.yaml`, lazy-loaded — every command still works
    with no config present): named pack sources, `site:` pointer, named
    `registries:` (placeholder for v0.3 phase C), `defaults.runtime`,
    `defaults.model`, tri-state `defaults.workspaceRoot`.
  - `kind: Site` (`site.yaml`): advisory `workspaceRoot`, `defaults`
    (runtime/model) split from `targetDefaults`, structured `packs:`
    (`{repo, subdir, ref}` or a bare local path string), `groups:` with shared
    `vars`, `bindingsDir:` (one level, sorted, filename stem must equal
    `metadata.name`, symlinked dir or files rejected, duplicate names rejected).
    `Binding` gained optional `spec.pack` / `spec.group` / `spec.runtime` fields.
  - `kind: SiteLock` (`site.lock.yaml`, committed next to `site.yaml`): per-pack
    `{repo, subdir, requestedRef, resolvedCommit}` (or `{local: true, path}`).
    `aoh lock` initializes entries that don't yet exist and never silently moves
    an existing one; `aoh lock --update [<pack>]` is the only mover and requires
    `--yes` (or interactive confirmation) on a source/ref change.
  - `src/aoh/gitops.py`: bare-mirror git cache keyed by a normalized-URL hash under
    `$AOH_HOME/cache`, fcntl-locked (`ensure_mirror`); `export_tree` preflights
    `git ls-tree` for symlink/submodule entries before any extraction, extracts
    into a private temp dir, verifies containment, then atomically renames onto
    the destination; `source_checkout` caches exports by
    `<urlhash>-<commit>-<subdirhash>-<format>` with a `.complete` marker written
    last (an incomplete export dir is wiped and re-exported).
  - `src/aoh/manifest.py` + `src/aoh/installer.py`: every install now writes
    `aoh-manifest.json` (source, resolved commit, per-file content hashes,
    canonical→materialized artifact map + adapter transform id, owned-file list,
    `namingScheme`). Installs are crash-safe and convergent: materialize into a
    staging dir, write a write-ahead journal (`.aoh-journal.json`, phase
    `staged`→`committing`, fsync'd at each transition) before touching the real
    workspace, back up every replaced/removed owned file, then commit; an
    interrupted install recovers to either "nothing happened" (phase `staged`) or
    "the new install completed" (phase `committing`, rolls forward) on the next
    run. Locally modified owned files refuse the install unless
    `--discard-local` is passed. ALL install paths — the legacy single-shot
    `aoh install --runtime … --output …` (recorded with `namingScheme:
    v1-legacy`) and the new site fan-out — route through the same
    `install_workspace`.
  - Site-qualified RBAC naming: bindings installed via a site fan-out get
    `ServiceAccount`/`ClusterRoleBinding` names of the form
    `aoh-<site>-<binding>` (DNS-1123 + 63-char validated); standalone (site-less)
    bindings keep the legacy `aoh-<binding>` name. Manifest records
    `namingScheme` (`v2-site-qualified` | `v1-legacy`).
  - `aoh install --site <dir> [--group <g>] [--binding <name>] [--workspace-root
    <dir>] [--accept-site-root] [--discard-local]`: fan-out install across every
    (or a filtered subset of) site bindings, each into
    `<effectiveRoot>/<binding-name>/`. Requires a lock that agrees with
    `site.yaml`'s source/ref (missing or disagreeing lock → error naming
    `aoh lock`). Per-binding failures are caught and isolated — other bindings
    still install, exit 1 if any failed.
  - `aoh list [--site <dir>] [--workspace-root <dir>]`: fleet table — binding,
    role, `pack@ref`, runtime, context/namespace, access, workspace path,
    provisioned state, credential state (from `aoh-provision.json` expiry).
    `--site` falls back to `UserConfig.site` when omitted.
  - `aoh config init|get|set <dotted.key> [value]`: manage `~/.aoh/config.yaml`
    (or `$AOH_HOME/config.yaml`).
  - `aoh lock [--site <dir>] [--update [<pack>]] [--yes]`: resolve every site
    pack ref to a commit and write/update `site.lock.yaml`.
  - `src/aoh/paths.py`: `safe_segment`/`safe_join` — every workspace-relative
    path (bindings dir entries, manifest `ownedFiles`/`artifactMap`, journal
    `stagingDir`/`backupDir`) is validated as non-escaping before use; nothing
    path-like from a manifest or journal is trusted without going through it.
  - `AOH_HOME` env var respected by every command that touches config, cache, or
    exports (defaults to `~/.aoh`).

### Changed

- Adapter contract standardized: `RuntimeAdapter.materialize` writes into
  EXACTLY `request.output_dir` for all three adapters (Hermes, Claude Code,
  Codex); the Hermes CLI's historical `<output>/<profile>/` nesting is now
  computed in the CLI handler before calling `materialize`, not inside the
  adapter. `AdapterResult` gained `artifact_map` (canonical pack-relative path →
  materialized path) and `transform_id` (e.g. `identity-v1`,
  `codex-ops-rename-v1`); `generated_files` is now a complete walk of every
  regular file under the output directory, not just pack-sourced ones.

- `RuntimeAdapter` Protocol (`materialize(MaterializeRequest) -> AdapterResult`) +
  `ADAPTERS` registry, extracted from the Hermes adapter — `src/aoh/adapters/base.py`.
- Claude Code runtime adapter: self-contained workspace (`.claude/skills`,
  `.claude/commands/ops/<skill>.md` → `/ops:<skill>`, `.claude/agents/<role>.md`,
  `.claude/settings.json` permission deny/allow + `PreToolUse` guardrail hook,
  `CLAUDE.md`).
- Codex runtime adapter: self-contained workspace (`.agents/skills/ops-<skill>/`
  with frontmatter `name` rewritten, invoked `$ops-<skill>`, `AGENTS.md`,
  `.codex/config.toml`, best-effort `.codex/rules/kubectl-readonly.rules`
  execpolicy guardrail with documented bypass gaps).
- `aoh install --runtime <hermes|claude-code|codex> <pack> --output <dir>` — unified
  CLI entrypoint into `ADAPTERS[<runtime>].materialize(...)`; old `install-hermes*`
  subcommands remain as unchanged compat handlers, `install-hermes-agent` prints a
  stderr deprecation hint.
- `Binding.access: scoped | inherit` (default `scoped`); `inherit` mode materializes a
  credential-free `kubeconfig-overlay` via `prepare-overlay.sh` (resolves cluster/user
  names from a redacted `kubectl config view`, never `--raw`; writes no credentials;
  self-verifies via `--minify` and a credential-shape grep).
- Live validation evidence: `docs/demos/adapter-validation-2026-07-16.md` — real
  `kind-sresquad-demo` cluster run proving the scoped RBAC boundary, the `auth can-i`
  matrix (including the `get secrets` → no flip), `codex execpolicy check` proofs for
  both caught and gap-form commands, and adversarial Claude Code hook proofs.
- `docs/adapters.md`: runtime adapters reference — workspace layouts, threat model,
  access modes, guardrail mapping per runtime.
- Documentation site (Docusaurus) — Concepts/Getting Started/Tutorials/Reference +
  Field Notes blog; GH Pages deploy.
- `collections/core/kubeops` pack: pod-crashloop-triage, pending-pod-triage,
  node-notready-triage, k8s-service-health-report skills + `kubeops-copilot` role.
- Minimal `kind: Binding` (role × target, open target map), loaded standalone from
  site repos — `examples/sresquad-site/` shows the shape.
- `aoh install-hermes-agent --binding <yaml>`: materializes the binding — generates
  `provision.sh` (dedicated read-only RBAC identity: get/list/watch), a scoped
  kubeconfig, KUBECONFIG wiring in launch.sh, and a binding block in SOUL.md.
- Demo walkthrough: `docs/demos/kubeops-readonly.md` (safe agentic harness showcase).

### Changed (BREAKING — spec v1alpha2)

- `apiVersion` is now `openagentix.io/v1alpha2`; v1alpha1 packs are rejected with a
  migration pointer. No compatibility shim.
- Removed `kind: Workflow`. Multi-skill workflows became process skills
  (`platform-sre-triage`, `devops-release-automation`, `mlops-training-triage`);
  single-skill wrappers were deleted. A stale `workflows/` dir is a validation error.
- Renamed `agents/` → `roles/` and `kind: AgentRole` → `kind: Role`; roles no longer
  carry a `workflows:` field. A stale `agents/` dir is a validation error.
- `Eval` now requires `spec.skill` pointing at the skill it tests.
- Hermes adapter generates one command per skill, namespaced `ops-<skill>.md`
  (canonical name `ops:<skill>`; separator mapping is per-adapter).
- Installed skill reference renamed `references/aoh-workflow.md` → `references/aoh-pack.md`.

### Changed (BREAKING — RBAC allowlist)

- ClusterRole `aoh-readonly` narrowed from a wildcard read grant
  (`apiGroups: ["*"], resources: ["*"], verbs: [get, list, watch]`) to an explicit
  resource allowlist sized to the kubeops skills (core/apps/batch/metrics/events.k8s.io
  kinds, get/list/watch only). `secrets`, `configmaps`, `nodes/proxy`, `pods/exec`,
  `pods/attach`, `pods/portforward`, `serviceaccounts/token`, RBAC objects, and
  `certificatesigningrequests` are explicitly excluded. Shared by every runtime
  adapter via `src/aoh/adapters/_k8s.py::render_provision_script`. **Any previously
  provisioned identity still has the old wildcard grant — re-run `provision.sh` for
  each existing binding to pick up the narrower allowlist** (it updates the
  ClusterRole in place; verified live: `auth can-i get secrets` flips from `yes` to
  `no`, see `docs/demos/adapter-validation-2026-07-16.md`).

### Changed
- Validator: progressive disclosure — only `AOH.yaml` + at least one skill are
  mandatory; workflows, agents, teams, models, evals, runtime-requirements are opt-in

### Added
- `.planning/` project memory system (GSD-compatible) + `CLAUDE.md` session protocol
- `planning-context` skill (`.claude/skills/planning-context`)

## [0.1.0] - 2026-07-13

### Added
- AOH pack format (`AOH.yaml` + skills/workflows/agents/teams/models/
  runtime-requirements/evals) with referential-integrity validator
- CLI: `validate`, `init-pack`, `adapt-hermes`, `install-hermes`,
  `install-hermes-agent`, `install-hermes-team`
- Hermes runtime adapter: generates `config.yaml`, `SOUL.md`, `aoh-agent.json`,
  `launch.sh`, profile-local skills, team manifests
- Example pack `examples/acme-platform-ops` (platform-ops team, 3 roles, 5 skills)
- Core collection `collections/core/docker-disk-cleanup` (first vertical slice)
- Authoring skill `authoring-skills/create-aoh-pack`

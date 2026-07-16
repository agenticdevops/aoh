# Changelog

All notable changes to AOH. Format: [Keep a Changelog](https://keepachangelog.com/),
versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added

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

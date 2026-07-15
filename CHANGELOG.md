# Changelog

All notable changes to AOH. Format: [Keep a Changelog](https://keepachangelog.com/),
versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added

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

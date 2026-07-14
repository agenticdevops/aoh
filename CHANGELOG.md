# Changelog

All notable changes to AOH. Format: [Keep a Changelog](https://keepachangelog.com/),
versioning: [SemVer](https://semver.org/).

## [Unreleased]

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

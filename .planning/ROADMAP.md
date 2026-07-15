# AOH Roadmap

Working style: superpowers-driven iteration (brainstorm → TDD → verify → ship).
`.planning/` is shared memory, not process ceremony. One phase = one shippable slice,
ideally one session.

## Milestone v0.1 — MVP ✅ (shipped 2026-07-13)

Pack format + validator + Hermes adapter producing launchable role profiles.
11 tests. Packs: `collections/core/docker-disk-cleanup`, `examples/acme-platform-ops`.

## Milestone v0.2 — Simplify + Solidify

| # | Phase | Goal | Status |
|---|-------|------|--------|
| 1 | Progressive disclosure | Skills-only pack validates; workflows/roles/teams/models optional | ✅ done |
| 2 | Collapse Workflow kind | Workflows become process skills; spec v1alpha2; migrate example packs | ✅ done |
| 2.5 | KubeOps pack + minimal Binding | kubeops pack; kind: Binding (role × target); RBAC read-only materialization; demo walkthrough + live RBAC denial proof | ✅ done |
| 3 | Adapter interface | Extract `RuntimeAdapter` protocol from hermes.py; CLI → `aoh install --runtime <x>` | pending |
| 4 | Drift model | Manifest w/ source ref + content hashes; `aoh status` / `sync` / `capture`; `--link` dev mode | pending |
| 5 | Claude Code adapter | Pack → skills + CLAUDE.md + agent defs; proves engine-neutrality | pending |
| 6 | Eval runner | Run pack evals against generated profiles; gate for cheap-model trust | pending |
| 7 | Binding layer | Full inventory pattern: binding groups, shared target vars, multi-target fan-out; site repo layout (minimal Binding shipped in 2.5) | pending |
| 8 | import-runbook | Skill factory: runbook file → SKILL.md + scripts + eval via frontier model | pending |

Phase order rationale: 1–2 shrink concept count before spec hardens; 3 must precede any
second adapter; 4 before more installs exist in the wild; 5 proves the neutrality claim;
6 unlocks the cheap-model story; 7–8 complete the product wedge.

## Milestone v0.3+ (parking lot)

- Codex adapter (`.agents/skills` + AGENTS.md), Goose adapter (recipes, native lead/worker
  models — first target for ModelProfile escalation), OpenCode adapter
- Registry/versioning, pack dependencies
- More vertical slices: k8s crashloop triage, terraform plan review, service health report,
  incident timeline, ML training triage
- Security fixes from CONCERNS.md: shell quoting in generated launch.sh, tilde expansion
- Skills library growth + agent examples: promote terraform-plan-review/incident-timeline
  to collections/, add example roles (k8s-oncall-sre, release-captain) composing them

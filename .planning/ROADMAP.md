# AOH Roadmap

Working style: superpowers-driven iteration (brainstorm → TDD → verify → ship).
`.planning/` is shared memory, not process ceremony. One phase = one shippable slice,
ideally one session.

## Milestone v0.1 — MVP ✅ (shipped 2026-07-13)

Pack format + validator + Hermes adapter producing launchable role profiles.
11 tests. Packs: `collections/core/docker-disk-cleanup`, `examples/acme-platform-ops`.

## Milestone v0.2 — Simplify + Solidify ✅ CLOSED (2026-07-17)

| # | Phase | Goal | Status |
|---|-------|------|--------|
| 1 | Progressive disclosure | Skills-only pack validates; workflows/roles/teams/models optional | ✅ done |
| 2 | Collapse Workflow kind | Workflows become process skills; spec v1alpha2; migrate example packs | ✅ done |
| 2.5 | KubeOps pack + minimal Binding | kubeops pack; kind: Binding (role × target); RBAC read-only materialization; demo walkthrough + live RBAC denial proof | ✅ done |
| 3 | Adapter interface | Extract `RuntimeAdapter` protocol from hermes.py; CLI → `aoh install --runtime <x>` | ✅ done |
| 5 | Claude Code adapter | Pack → skills + CLAUDE.md + agent defs; proves engine-neutrality | ✅ done (Codex adapter shipped alongside, ahead of schedule) |
| — | Docs site | Docusaurus site (`docs-site/`) — Concepts/Getting Started/Tutorials/Reference sections, 3 hand-drawn reveal.js decks, Field Notes blog, GH Pages deploy workflow | ✅ done |

Phases 4 (Drift model), 6 (Eval runner), 7 (Binding layer), 8 (import-runbook) from the
original v0.2 table did not ship under v0.2 — 4 and 7 folded into v0.3 phase A (below,
drift-manifest foundation moved earlier per the 2026-07-14 "drift before installs
multiply" decision); 6 (eval runner) and 8 (import-runbook) moved to v0.4 parking.

## Milestone v0.3 — Fleet Lifecycle

Design: `.planning/design/2026-07-17-v03-fleet-lifecycle-design.md` (v2, cross-AI
reviewed — codex gpt-5.6-sol, round 1 REWORK/12 findings, round 2
APPROVE-WITH-CHANGES). Plan: `docs/plans/2026-07-17-v03-phase-a-foundation.md` (v2,
plan-level cross-AI review — REWORK/14 findings → APPROVE).

Vision: draft skill locally → use immediately → promote to pack repo (git = truth) →
publish (registry index) → pin + lock (site repo) → materialize fleet (adapters) →
operate in-session (console) → improve → capture back → loop. Ansible frame:
role⇄skill, collection⇄pack, inventory⇄site, galaxy⇄registry, control node⇄console.

| # | Phase | Goal | Status |
|---|-------|------|--------|
| A | Foundation | UserConfig + Site inventory, git source resolution (mirror cache), manifest-backed crash-safe convergent installs (all install paths), site-qualified RBAC naming, `aoh install --site` fan-out + `aoh list` + `aoh config` + `aoh lock` (minimal lock) | ✅ done (2026-07-17, SDD, commits `9750a3c`→`3e657df`, 307 tests) |
| B | Authoring/promote | Draft local, promote central — `collections/core/aoh-authoring` skill pack; `aoh skill promote` (bare-mirror + lock + temp worktree + FF-only git flow, direct-commit default / `--pr` opt-in) | pending |
| C | Registry + lock | `aoh-registry` index; named/ordered `registries:` in UserConfig; full `site.lock.yaml` (registry, source, subdir, ref, resolved commit, treeSha256); `aoh lock --update` moves it | pending |
| D | Drift: status/sync/capture | Five-state compare (CURRENT/BEHIND/MODIFIED/CONVERGED/DIVERGED) per owned file; `aoh status` (read-only); `aoh sync [--merge]`; `aoh capture` (inverse-transform via manifest map, validate, promote) | pending |
| E | Fleet console | `aoh console --site … --output <dir>` — Claude Code runtime, `access: scoped` bindings only; generates `provision-all.sh`, per-binding kubeconfig slots, fleet skill + kubectl-guard, rendered CLAUDE.md inventory; never executes | pending |

Phase order rationale: A carries the drift-manifest foundation forward (our own
2026-07-14 "drift before installs multiply" decision) so it precedes any fan-out
that could accumulate un-tracked installs; B before C — promotion needs somewhere
to publish to, but registry/lock hardening can follow; D needs A's manifest and
C's lock to compare against; E is last because it concentrates credentials across
an entire fleet and deliberately waits until locking + drift are solid.

## Milestone v0.4 (parking lot)

- Goose adapter (recipes, native lead/worker models — first target for ModelProfile
  escalation), OpenCode adapter (Codex adapter shipped in v0.2 phase 5, ahead of
  schedule)
- Registry search / public discovery (named-registry + lock retained in v0.3 phase C;
  search and public discovery explicitly cut from v0.3 per cross-AI review)
- Codex console, inherit-mode console (v0.3 phase E is claude-code + scoped-only only)
- Eval runner: run pack evals against generated profiles; gate for cheap-model trust
  (was v0.2 phase 6)
- import-runbook: skill factory, runbook file → SKILL.md + scripts + eval via frontier
  model (was v0.2 phase 8)
- Pack dependencies/imports (Galaxy-style)
- More vertical slices: k8s crashloop triage, terraform plan review, service health report,
  incident timeline, ML training triage
- Security fixes from CONCERNS.md: shell quoting in generated launch.sh, tilde expansion
- Skills library growth + agent examples: promote terraform-plan-review/incident-timeline
  to collections/, add example roles (k8s-oncall-sre, release-captain) composing them

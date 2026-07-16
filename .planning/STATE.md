# AOH State

> Session bootstrap: read this file, then ROADMAP.md, then PROJECT.md decisions table.
> Everything here survives /clear — trust these files over memory.

## Position

- Milestone: v0.2 (Simplify + Solidify)
- Current phase: 2.5 (KubeOps pack + minimal Binding) — ✅ done
- Next action: phase 3 (Adapter interface) — extract `RuntimeAdapter` protocol from
  hermes.py, CLI → `aoh install --runtime <x>`. Live RBAC demo done 2026-07-15
  (provision + Forbidden proof on kind-sresquad-demo); agent-chat walkthrough
  (docs/demos/kubeops-readonly.md §4) still open for user
- Docs site (`docs-site/`) shipped 2026-07-16, not yet deployed — Pages needs to be
  enabled and `.github/workflows/docs-deploy.yml` pushed with a `workflow`-scoped token
  (see that session log entry)

## Repo facts

- Remote: https://github.com/agenticdevops/aoh.git (main tracks origin/main)
- Nested repo inside `experiments/` parent tree (parent gitignores `aoh/`)
- Test command: `rtk proxy uv run pytest -q` — 31 passing (v0.2 phase 2.5 + review fixes)
- Validate: `uv run aoh validate <pack>`

## Session log

### 2026-07-16 — docs site built + deploy wired (Docusaurus, subagent-driven development)
- Built via subagent-driven development: 7 tasks, each with a review, plus a final
  whole-branch review — same loop AOH uses to build its own packs
- `docs-site/` scaffolded (Docusaurus + TypeScript, `onBrokenLinks: 'throw'` build gate)
  with Concepts, Getting Started, Tutorials, and Reference sections — every page traces
  to a real repo source file; roadmap-only features (drift status/sync/capture,
  `install --runtime`, non-Hermes adapters) explicitly marked "planned," not documented
  as shipped
- 3 hand-drawn reveal.js decks embedded via a custom `Slides` component: what-is-aoh,
  core-model, safe-agents
- Interactive `Quiz` component used on tutorial pages; mermaid diagrams enabled
- Field Notes blog live at `/field-notes`: 3 grounded seed posts (workflow-kind
  collapse, the read-only kubernetes RBAC proof + the shell-injection fix caught in
  review, and this docs site's own build) + `tags.yml`
- Real landing `docs/intro.mdx`: 60-second pitch, deck embed, start-here grid
- GH Pages deploy workflow added (`.github/workflows/docs-deploy.yml`); NOT pushed —
  needs a `workflow`-scoped token and Settings → Pages → Source = GitHub Actions
  before the first Actions run publishes to https://agenticdevops.github.io/aoh/
- Build verified: `npm --prefix docs-site run build` exits 0, zero broken links

### 2026-07-15 — kubeops pack + minimal Binding shipped (phase 2.5, subagent-driven development)
- Executed via subagent-driven development: 4 tasks, each with a clean review
- 9df57bc `collections/core/kubeops` pack: pod-crashloop-triage, pending-pod-triage,
  node-notready-triage, k8s-service-health-report skills + `kubeops-copilot` role
- 1bbf112 minimal `kind: Binding` model in pack.py (role × target, open target map),
  loaded standalone from site repos
- 3ae3ebf Hermes materialization: `aoh install-hermes-agent --binding` generates
  provision.sh (dedicated read-only RBAC identity: get/list/watch), scoped kubeconfig,
  KUBECONFIG wiring in launch.sh, binding block in SOUL.md
- Site example `examples/sresquad-site/` + demo walkthrough
  `docs/demos/kubeops-readonly.md` (safe agentic harness showcase)
- docs/spec.md updated: `Binding` artifact kind, layout note, validation rule
- Final suite: 29 passing; all three packs (kubeops, docker-disk-cleanup,
  acme-platform-ops) validate clean

### 2026-07-14 — spec v1alpha2 shipped (phase 2, subagent-driven development)
- Executed via subagent-driven development: 5 tasks, each with a clean review
- 940fd02 pack migration (multi-skill workflows → process skills, drop 1:1 wrappers)
- c3a6470 excise `kind: Workflow`; Hermes emits `commands/ops-<skill>.md` per skill
- 6e1de52 evals require `spec.skill`; 2c80ec6 `agents/`→`roles/`, `AgentRole`→`Role`
- c7def8c hard cut to `apiVersion: openagentix.io/v1alpha2` (no compat shim)
- Docs pass (task 6): docs/spec.md full rewrite for v1alpha2 + Migration Notes section
  (closes pack.py's "see docs/spec.md migration notes" pointer), README + hermes-adapter.md
  + authoring.md swept for stale workflow/agents/v1alpha1 vocabulary, CHANGELOG updated
- Final suite: 18 passing

### 2026-07-14 — audit, design review, repo sync, planning system
- Independent audit: brief verified accurate; 11/11 tests, packs valid, Hermes profiles live
- Found + fixed orphan repo: init'd, attached agenticdevops/aoh, reconciled (LICENSE
  restored), pushed .planning/codebase docs (2c53306); untracked aoh/ from parent repo
- Design review → .planning/design/2026-07-14-design-review.md (drift model, kill
  Workflow, progressive disclosure, Binding layer)
- Built this planning system + CLAUDE.md + planning-context skill
- Working style set: superpowers for iteration speed; .planning/ = shared memory,
  not GSD ceremony
- Phase 1 shipped (TDD): validator no longer requires workflows — skills-only packs
  valid; 13 tests green; spec.md synced; pushed as c7a2923

## Handoff notes

- Untracked at root: docker-disk-cleanup-report*.html — generated artifacts, decide
  delete vs gitignore
- `.deepeval/` dir exists — from earlier experimentation, not wired into anything

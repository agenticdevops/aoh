# Design Review — 2026-07-14

Independent audit + design review of AOH MVP. Verdict: **direction right, wedge right,
three structural flaws to fix before they ossify.**

## Verified state

- 11/11 tests pass; both packs validate; 6 CLI commands work
- Hermes adapter generates config.yaml, SOUL.md, aoh-agent.json, launch.sh, team manifest
- Live profiles in ~/.hermes/profiles (acme-platform-*, aoh-docker-disk-cleanup)
- 1512 LOC. Repo synced to agenticdevops/aoh (was orphan checkout — fixed, pushed)

## Flaw 1 — Copy-install drift (biggest)

`hermes.py` uses `copytree`: install = fork. Agent edits installed skill → orphaned,
lost on reinstall. Ansible analogy misleading here: Ansible pushes to stateless targets;
AOH installs into stateful agent-edited configs (Helm/dotfiles drift problem).

Fix (GitOps model, pack repo = source of truth):
- Extend aoh-agent.json manifest: pack source ref + git sha + per-skill content hash
- `aoh status` (drift detect), `aoh sync` (pack → profile), `aoh capture` (profile edits
  → pack as diff/PR — the killer loop: agent improves skill during incident, captured,
  reviewed, whole team gets it)
- `--link` symlink dev mode

## Flaw 2 — Workflow kind is redundant

Verified: workflows carry zero steps/logic — pure reference bundles duplicating role
fields. Superpowers got it right: workflows ARE skills (process skill referencing other
skills). Kill the kind, fold content into process-skill SKILL.md.

## Flaw 3 — Everything mandatory

Validator required ≥1 workflow (+ skills). 8 kinds as entry tax. Fix: progressive
disclosure — layers 0-3 (skills → pack → org → bindings), only AOH.yaml + skills
mandatory. Solo dev in 5 min; enterprise grows into org layers. (Phase 1 shipped this.)

## Missing layer — Binding/inventory (the WHERE)

AOH models WHO (org/team/role) not WHERE (cluster/env/account). Ansible split: roles
reusable/shared, inventory site-specific/private. Add `kind: Binding`: role × target →
generated profile (e.g. sre-platform @ acme-prod-gke → launch.sh with kube context).
Profiles = role × binding, generated, disposable. Secrets stay out — declare requirement,
runtime/env/vault provides.

## Cheap/frontier model split — assessment

Right instinct; DNA already present (`local-worker` fallback → `frontier-unblocker`,
deterministic scripts in skills). But nothing enforces it — ModelProfile is aspirational
metadata. Eval runner is the linchpin of trust. Goose native lead/worker = first real
mapping target. `aoh import-runbook` = the demo that sells the product.

## Alternatives considered and rejected

- Per-runtime skills, no harness: dies at 2nd runtime, no org model
- Thin format converter only: commodity, weekend project, loses differentiation
- Own runtime: correctly rejected already
- MCP-first: MCP = tools, runbooks = process/knowledge → skills correct; MCP complements

## Superpowers comparison

Superpowers = one artifact kind, single runtime, personal, git-backed, invocation
discipline. AOH = packaging/org/distribution across runtimes. Complementary layers.
AOH inherits skill format + process-skill pattern; adds distribution, model routing,
evals, org model — as opt-in layers, keeping Superpowers-grade entry simplicity.

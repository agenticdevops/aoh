---
gsd_state_version: 1.0
milestone: v0.3
milestone_name: — Fleet Lifecycle
status: unknown
last_updated: "2026-07-25T19:11:57.787Z"
---

# AOH State

> Session bootstrap: read this file, then ROADMAP.md, then PROJECT.md decisions table.
> Everything here survives /clear — trust these files over memory.

## Position

- Milestone: v0.3 (Fleet Lifecycle)
- Current phase: B (Authoring/promote) — ✅ done
- Next action: phase C (Registry + lock) — `aoh-registry` index; named/ordered
  `registries:` in UserConfig; full `site.lock.yaml` (registry, source, subdir, ref,
  resolved commit, treeSha256); `aoh lock --update` moves it

- v0.2 CLOSED 2026-07-17 (see ROADMAP.md). Docs site LIVE at
  https://agenticdevops.github.io/aoh/ (Pages deploy green 2026-07-16;
  auto-redeploys on push touching docs-site/**).

## Repo facts

- Remote: https://github.com/agenticdevops/aoh.git (main tracks origin/main)
- Nested repo inside `experiments/` parent tree (parent gitignores `aoh/`)
- Test command: `rtk proxy uv run pytest -q` — 365 passing (v0.3 phase B: gitops
  write primitives, skillcopy hygiene, promote orchestration, `aoh skill promote`
  CLI, aoh-authoring pack)

- Validate: `uv run aoh validate <pack>`

## Session log

### 2026-07-27 — v0.3 phase B shipped: authoring/promote (SDD)

- Executed via SDD (spec-driven development): 6 implementation tasks + this docs
  task, commits `be42725`→`494e4cf` — `feat: gitops write primitives — fetch,
  worktree, identity check, FF push, PR` (B1), `feat: skillcopy — hygiene-filtered
  skill tree copy` (B2), `feat: promote orchestration — worktree-staged validate,
  commit/PR, fast-forward conflict detection` (B3), `feat: aoh skill promote CLI`
  (B4), `feat: aoh-authoring pack — draft-then-promote skill` (B5), `docs: live
  promote validation — scratch repo, direct commit + PR path` (B6)

- New modules: `src/aoh/gitops.py` gained write primitives (`fetch_default_branch`,
  `create_worktree`/`remove_worktree`, `check_identity`, `commit_all`,
  `push_fast_forward`, `create_branch`, `push_branch`, `set_remote_url`,
  `staged_diff`, `open_pr`); `src/aoh/skillcopy.py` (new — hygiene-filtered skill
  tree copy: rejects `.git`, symlinks, devices/sockets/fifos, oversized files,
  enforces file-count/total-size caps, single pre-scan pass so a violation leaves
  nothing written); `src/aoh/promote.py` (new — orchestrates discover → worktree →
  copy → validate → commit/PR, wraps git/copy errors as `PromoteError`)

- `aoh skill promote <name> [--from DIR] --pack <name> [--pr]` shipped: direct-commit
  default (fast-forward push to the real pack repo, not just the mirror), `--pr`
  opt-in (feature branch + `gh pr create`); prints the staged diff before announcing
  success; no-op re-promote detected via git's own "nothing to commit" rather than a
  persisted state; a non-fast-forward push rejection is treated as the conflict
  signal and surfaces "re-run with --pr" — no auto-retry, no force-push

- `collections/core/aoh-authoring` pack shipped: one skill
  (`author-and-promote-skill`) that walks an agent through validating a draft,
  finding the target pack, running `scripts/promote.sh` (a thin `exec aoh skill
  promote "$@"` wrapper — the skill stays declarative, doesn't hardcode shell),
  reading the staged diff before it ships, and reporting the result

- Live validation (`docs/demos/promote-validation-2026-07-19.md`) against a real,
  private, throwaway GitHub repo (`initcron/aoh-promote-scratch-*`, never the real
  `agenticdevops/aoh` repo): direct-commit promote landed a real commit
  (`9b2c42aafb`), a re-promote produced no new commit (3 total commits on `main`,
  no room for a 4th), and `--pr` opened a real PR (#1, merged) — also surfaced and
  documented an `open_pr` bug found during the live `--pr` run (PR merge completed
  manually after the bug surfaced; recorded honestly rather than papered over)

- Design ambiguity resolved inline (not deferred): "promotion base" for conflict
  detection is the fresh-fetch tip at the start of each promote, not a persisted
  cross-session ledger — the fast-forward push itself is the conflict check. YAGNI
  for a single-operator v1; a persisted multi-skill base ledger is deferred to
  Phase D if concurrent multi-operator promotion needs it later.

- A real gotcha found via TDD, worth remembering: a worktree cut from a `--mirror`
  clone inherits an `origin` remote with `remote.origin.mirror = true`, which
  forbids explicit refspecs on push — every push from such a worktree must
  either override that config inline (`-c remote.origin.mirror=false`, used by
  `push_fast_forward` against the mirror) or push by URL (never by remote name)
  once `set_remote_url` has repointed `origin` at the real repo (used by
  `push_branch`/the `--pr` path) — pushing by name after repointing is unsafe
  because the mirror-inherited config still lingers on that remote entry.

- Docs: this task — ROADMAP phase B → done / phase C next, PROJECT.md decision rows
  (conflict-detection-via-fresh-fetch, skillcopy hygiene limits, the mirror-worktree
  URL-not-name push gotcha, aoh-authoring's script-wrapper pattern), CHANGELOG
  [Unreleased] Added, new `docs/promote.md`, docs-site
  `docs/tutorials/authoring-and-promoting.mdx` (new, quiz) + `docs/reference/cli.md`
  (`aoh skill promote` section) + field note `blog/2026-07-27-draft-to-promote.md`

- Final suite: 365 passing; all 4 packs validate (docker-disk-cleanup, kubeops,
  acme-platform-ops, aoh-authoring); docs-site build exit 0

### 2026-07-17 — v0.3 phase A shipped: fleet inventory, lock, convergent installs (SDD)

- Executed via SDD (spec-driven development): 7 implementation tasks + this docs
  task, commits `9750a3c`→`3e657df` — `feat: paths + site inventory` (A1),
  `feat: gitops — mirror cache, preflighted safe export` (A2), `feat: adapter
  contract — exact output dir + complete artifact inventory` (A3), `feat: manifest +
  crash-safe convergent installer wired into all installs` (A4), `feat:
  site-qualified RBAC identity naming` (A5), `feat: site lock + fan-out install,
  list, config, lock CLI` (A6), `test: site fan-out e2e — locked git-sourced
  packs` (A7)

- New modules: `src/aoh/paths.py` (`safe_segment`/`safe_join`, containment-checked
  path joins), `src/aoh/site.py` (`UserConfig`, `Site`, `SiteGroup`, `PackSource`,
  `SiteLock`/`LockedPack`, `resolve_binding_settings` precedence), `src/aoh/gitops.py`
  (bare-mirror cache keyed by URL hash, fcntl-locked, preflighted symlink/submodule-
  safe `export_tree`, format-versioned export cache), `src/aoh/manifest.py`
  (`aoh-manifest.json` build/read/write, atomic tmp+rename, path-validated on read),
  `src/aoh/installer.py` (`install_workspace` — write-ahead journal, staged→committing
  phases, crash recovery, per-file backup-before-overwrite, fcntl install lock)

- Cross-AI design + plan review (external reviewer: codex gpt-5.6-sol) — design 2
  rounds (v1 REWORK/12 findings → v2 APPROVE-WITH-CHANGES, final amendments binding);
  plan 1 round (REWORK/14 findings, all adjudicated → v2 APPROVE)

- F1 supply-chain lock proof (live, in `tests/test_site_e2e.py`): a git-sourced
  `kubeops` pack served from a local bare repo, locked via `aoh lock`; pushing a new
  commit upstream and re-running `aoh install --site` (no `--update`) still installs
  the OLD locked commit — the movable `main` ref changing upstream does not affect an
  unlocked re-install. `aoh lock --update` then moves the pin; re-install picks up
  the new commit, and a further commit removing a file converges both workspaces
  (stale owned file removed, not just new files added) — proves the lock is the real
  install authority, not `site.yaml`'s ref.

- Site-qualified RBAC naming shipped in phase A (not deferred to E per the design's
  open question): `aoh-<site>-<binding>` when installed via a site fan-out,
  `aoh-<binding>` legacy naming preserved for standalone bindings; manifest records
  `namingScheme` (`v2-site-qualified` | `v1-legacy`).

- Docs: this task — ROADMAP v0.2 closed / v0.3 phase table, PROJECT.md decision rows,
  CHANGELOG [Unreleased], `docs/spec.md` UserConfig/Site/SiteLock summaries, new
  `docs/installs.md` (crash-safe convergent install model), docs-site
  `docs/reference/site.md` (new) + `docs/reference/cli.md` (install --site/list/
  config/lock) + `docs/tutorials/bindings-inventory.mdx` (real site.yaml walkthrough
  replacing the old hypothetical framing), field note
  `blog/2026-07-17-fleet-inventory.md`

- Final suite: 307 passing; all 3 packs validate; docs-site build exit 0

## Session log (v0.2)

### 2026-07-16 — Claude Code + Codex adapters shipped (phases 3+5, SDD)

- Executed via SDD (spec-driven development): protocol extraction, both adapters,
  unified CLI, inherit mode, docs — commits `31d90b4`, `25afdc8`, `6e8f523`+`8b02708`,
  `ec0f6f8`, `770c999`, `19a82e3`

- `RuntimeAdapter` Protocol + `ADAPTERS` registry extracted from hermes.py
  (`src/aoh/adapters/base.py`); Claude Code adapter (`.claude/skills`,
  `.claude/commands/ops/<skill>.md` → `/ops:<skill>`, `.claude/agents/<role>.md`,
  `.claude/settings.json` deny/allow + fail-closed `PreToolUse` `kubectl-guard.sh`
  hook, `CLAUDE.md`); Codex adapter (`.agents/skills/ops-<skill>/` with frontmatter
  `name` rewritten, invoked `$ops-<skill>`, `AGENTS.md`, `.codex/config.toml`,
  best-effort `.codex/rules/kubectl-readonly.rules` execpolicy guardrail with 3
  documented bypass gaps)

- Unified CLI: `aoh install --runtime <hermes|claude-code|codex> <pack> --output <dir>`
  routes into `ADAPTERS[<runtime>].materialize(...)`; old `install-hermes*`
  subcommands kept as unchanged compat handlers, `install-hermes-agent` prints a
  stderr deprecation hint

- `Binding.access: scoped | inherit` (default `scoped`); inherit mode writes NO
  credentials — `prepare-overlay.sh` resolves cluster/user names from a redacted
  `kubectl config view` (never `--raw`), self-verifies via `--minify` + a
  credential-shape grep

- ClusterRole `aoh-readonly` narrowed from a `*/*` wildcard to an explicit
  get/list/watch resource allowlist (Secrets, configmaps, nodes/proxy, pods/exec
  excluded) — BREAKING for previously provisioned identities, shared across all three
  adapters via `src/aoh/adapters/_k8s.py`

- Design went through cross-AI review (external reviewer: codex gpt-5.6-sol),
  3 rounds — v1 approved in brainstorming, v2 REWORK (12 findings, all adjudicated),
  convergence round APPROVE-WITH-CHANGES, third round (user-relayed critical review on
  installed codex-cli 0.144.5) added the execpolicy rules file + documented gaps

- Live validation against `kind-sresquad-demo` (real cluster, not just unit tests):
  headline proof is `kubectl auth can-i get secrets` flipping from `yes` (old wildcard
  role) to **no** (new allowlist) after re-running `provision.sh`; full transcript incl.
  `codex execpolicy check` proofs (caught + 3 gap forms) and adversarial Claude Code
  hook proofs in `docs/demos/adapter-validation-2026-07-16.md`

- Docs: `docs/spec.md` Commands table flipped to shipped + corrected Codex surface
  (`.agents/skills/ops-<skill>/`, not `prompts/`); new `docs/adapters.md` (workspace
  layouts, threat table, guardrail mapping, the compound-Bash-command hook caveat);
  CHANGELOG updated

- Final suite: 114 passing; all 3 packs (kubeops, docker-disk-cleanup,
  acme-platform-ops) validate clean

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

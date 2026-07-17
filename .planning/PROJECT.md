# AOH — Agentic Ops Harness

## Vision

Engine-neutral harness for agentic DevOps/SRE/Platform/MLOps. "Superpowers for Ops."
Convert runbooks into portable, evaluated, git-versioned skills that cheap/local models
execute repeatably, with frontier models reserved for authoring skills and unblocking
complex tasks. One pack format, many runtimes (Hermes today; Claude Code, Codex, Goose,
OpenCode next).

- Umbrella: OpenAgentix / OpsFlow LLC
- Repo: https://github.com/agenticdevops/aoh.git
- Mental model: Ansible-like (packs ≈ roles, bindings ≈ inventory) — but AOH organizes,
  packages, validates, adapts. It never executes. Runtimes execute.

## Core Model

```
Org / BU / Project
  -> Team -> Role -> Skills / ModelProfile / RuntimeRequirements / Evals
  -> Runtime Adapter (hermes | claude-code | codex | goose | opencode)
  -> Binding (role × target: cluster/env/account)   [planned]
```

## The Killer Feature

Runbook → frontier model authors SKILL.md + deterministic scripts + eval →
`aoh validate` + eval runner gate it → local/cheap worker model executes →
escalates to frontier-unblocker when stuck. Evals are what make cheap-model
execution trustworthy.

## Layered Simplicity (decided 2026-07-14)

Progressive disclosure — Superpowers-simple at entry, org model opt-in:

- Layer 0: `skills/` — pure agentskills standard, works with zero AOH
- Layer 1: `AOH.yaml` — pack = distribution unit (name, version)
- Layer 2: `agents/ teams/ models/ evals/ runtime-requirements/` — org layer, opt-in
- Layer 3: bindings — role × cluster/env, org-private repo, opt-in

Minimum viable pack = AOH.yaml + one skill. Five minutes to value.

## Key Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-07-13 | Engine-neutral; AOH is not a runtime | Runtimes execute; AOH organizes/packages/validates/adapts |
| 2026-07-13 | Skills use agentskills SKILL.md format | Riding the converging de-facto standard, not inventing one |
| 2026-07-13 | Guardrail engine deferred | Declare intent in RuntimeRequirement; adapters map to native guardrails |
| 2026-07-14 | Kill `Workflow` kind → process skills | Workflows carried zero steps/logic — pure duplication of role refs. Superpowers pattern: workflows ARE skills |
| 2026-07-14 | Progressive disclosure; only AOH.yaml + skills mandatory | 8 mandatory kinds = entry tax; solo dev must get value in 5 min |
| 2026-07-14 | GitOps drift model, pack repo = source of truth | `copytree` install = fork; agent edits orphaned. Need manifest hashes + status/sync/capture |
| 2026-07-14 | Context targeting via Binding layer (role × target) | Pack stays portable (the WHO); binding is site-specific (the WHERE), Ansible inventory split |
| 2026-07-14 | Secrets out of scope | Declare requirement; runtime/env/vault provides. Never store |
| 2026-07-14 | Adapter interface before adapter #2 | Prevent Hermes conventions ossifying into core; CLI → `aoh install --runtime <x>` |
| 2026-07-14 | Planning/context lives in .planning/ markdown (GSD-compatible) | Survives /clear; project memory outside agent context window |
| 2026-07-14 | v1alpha2: hard cut, no v1alpha1 compat | Alpha = zero compat promise; dual-version validator = permanent tax |
| 2026-07-14 | `agents/` → `roles/`, kind `AgentRole` → `Role` | Role = real-world WHO; avoids "agent" overload; cheapest before adapter #2 |
| 2026-07-14 | Eval links to skill via required `spec.skill` | Skill+eval travel together; eval gates cheap-model trust per skill |
| 2026-07-14 | Command namespace prefix `ops` (user decision) | Easier to type than `aoh`; canonical `ops:<skill>`, separator per adapter; conflicts = other tools' problem |
| 2026-07-15 | Binding pulled forward minimally (role × target, open target map) | kubeops test needs cluster context injection; ad-hoc CLI flags would be throwaway |
| 2026-07-15 | Read-only agents enforced via RBAC-scoped kubeconfig, AOH generates provision.sh, user executes | Strongest native guardrail, runtime-agnostic, separate agent identity + audit; preserves "AOH never executes" |
| 2026-07-15 | Hermes NOT used for kubectl enforcement | Verified from source: hardcoded pattern list, zero kubectl awareness, no subcommand allow/deny config |
| 2026-07-15 | Transparent proxy enforcement rejected for v1 | Guards endpoint not credential; user identity; live process; noted as future spec.enforcement alternative |
| 2026-07-16 | `RuntimeAdapter.materialize(request: MaterializeRequest) -> AdapterResult` — single method, runtime-specific options validated by the adapter (not the protocol); `AdapterResult` carries `diagnostics: list[str]` | Review finding: `profile/provider/cwd` in the original sketch were Hermes-isms; adapters need a way to warn on unenforceable requirements instead of silently claiming enforcement |
| 2026-07-16 | `Binding.access: scoped \| inherit` (default `scoped`); inherit resolves cluster/user names via redacted `kubectl config view` and writes a credential-free overlay, never a credential snapshot | Snapshot approach broke exec-plugin auth (e.g. gke-gcloud-auth-plugin) and violated the "never store secrets" decision (2026-07-14) |
| 2026-07-16 | Threat model stated as "hard enforcement boundary" (cluster RBAC) vs. "best-effort runtime guardrail" (per-runtime), never as wall-counting language | Review finding: counting "two walls" implied guardrails were containment; honest 3-column table (boundary / guardrail / required assumptions) prevents operators mistaking a guardrail for a security boundary |
| 2026-07-16 | ClusterRole `aoh-readonly` is an explicit get/list/watch resource allowlist, not `*/*` wildcard; Secrets, configmaps, nodes/proxy, pods/exec/attach/portforward, serviceaccounts/token, RBAC objects, CSRs all explicitly excluded | Wildcard read granted every Secret in the cluster to the "read-only" agent identity — contradicted the read-only claim; allowlist sized to the four kubeops skills plus deliberate small headroom for free-form triage |
| 2026-07-16 | Cross-AI design review loop used for adapter design (external reviewer: codex gpt-5.6-sol) — 3 rounds (initial REWORK/12 findings, convergence APPROVE-WITH-CHANGES, user-relayed critical review adding the Codex execpolicy rules file) before implementation | High-stakes security-adjacent design (RBAC boundary + guardrail claims); independent adversarial review caught real gaps (Bash() pattern bypasses, snapshot-credential risk, overstated "no kubectl guardrail" claim for Codex) that internal review missed |
| 2026-07-17 | Workspace-root ownership: effective root = `--workspace-root` CLI flag > `UserConfig.workspace_root` (tri-state: unset/None is a real, distinct value) > site's `workspaceRoot` (ADVISORY, used only with `--accept-site-root`) > `~/agents` default; whichever wins, one loud stderr notice is printed | A remote site file (pulled from someone else's git repo) must never silently direct filesystem writes on the operator's own machine — consent has to be explicit, and a missing user config must be distinguishable from an explicit empty one |
| 2026-07-17 | Crash-safe convergent install with write-ahead journal (`.aoh-journal.json`, phase staged→committing, fsync'd at each phase transition) — ALL install paths (legacy single-shot AND site fan-out) route through the same `install_workspace` | `copytree`-style installs accrete forked, orphaned files at fleet scale; a bare "atomic swap" claim doesn't survive an interrupted per-file copy, so recovery is phase-explicit: `staged` = nothing mutated yet (clean abort), `committing` = roll forward using the journal's embedded `newManifest`, never recomputed |
| 2026-07-17 | Site-qualified RBAC naming (`aoh-<site>-<binding>`) shipped in phase A, before any real fleet exists; standalone (site-less) bindings keep the legacy `aoh-<binding>` name; manifest records `namingScheme` (`v2-site-qualified` \| `v1-legacy`) | Cross-site collisions are a real risk once fan-out exists (two sites, same binding name); renaming identities after a fleet is already provisioned is disruptive, so the naming scheme change lands as early as possible and is versioned so old and new installs stay distinguishable |
| 2026-07-17 | Structured `PackSource` (`{repo, subdir, ref}`, plus a bare string = local path) replaces `//subdir`-suffixed strings; `site.lock.yaml` (`kind: SiteLock`) pins each pack to a `resolvedCommit` — installs resolve through the LOCK, never re-resolve `site.yaml`'s ref; `aoh lock` initializes only (never moves an existing entry), `aoh lock --update [pack]` is the only mover and requires `--yes` on a source/ref change | `//` was URL-ambiguous; movable refs (`main`) are "tracking refs," not pins — a site.yaml ref moving upstream must not silently change what an unlocked re-install materializes (proven live in `tests/test_site_e2e.py`: pushing a new commit and re-installing without `aoh lock --update` still installs the old locked commit) |
| 2026-07-17 | New kinds `UserConfig` (`~/.aoh/config.yaml`, lazy-loaded — every existing command still works with no config present), `Site` (`site.yaml` — workspace root advisory, defaults, target defaults, packs, groups, bindingsDir), `SiteLock` (`site.lock.yaml`, committed next to `site.yaml`) | Ansible-inventory split extended: `UserConfig` is the operator's own machine-local defaults, `Site` is the fleet's shared, versioned inventory, `SiteLock` is the supply-chain pin that makes the inventory's git-sourced packs reproducible |

## Open Questions

- Team defaults override role model profiles?
- ModelProfile escalation semantics (`fallback:`) — which adapter enforces first? (Goose has native lead/worker)
- Minimum viable registry format; pack dependencies/imports (Galaxy-style)?
- MCP UI for interactive ops workflows?

## Constraints

- Python + uv; PyYAML runtime dep; pytest dev dep
- Semver tags; update CHANGELOG.md before every release
- Tests: `rtk proxy uv run pytest -q` (plain `rtk pytest` doesn't collect in uv projects)

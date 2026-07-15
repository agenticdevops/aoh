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

## Open Questions

- Team defaults override role model profiles?
- ModelProfile escalation semantics (`fallback:`) — which adapter enforces first? (Goose has native lead/worker)
- Minimum viable registry format; pack dependencies/imports (Galaxy-style)?
- MCP UI for interactive ops workflows?

## Constraints

- Python + uv; PyYAML runtime dep; pytest dev dep
- Semver tags; update CHANGELOG.md before every release
- Tests: `rtk proxy uv run pytest -q` (plain `rtk pytest` doesn't collect in uv projects)

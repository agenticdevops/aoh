# Spec v1alpha2 Design — Workflow Collapse + Role Rename

Date: 2026-07-14. Phase 2 of milestone v0.2. Approved in brainstorming session.

## Goal

Kill the `Workflow` kind (pure duplication of role refs — carried zero steps/logic),
rename `agents/` → `roles/`, bump spec to `openagentix.io/v1alpha2`. Fewer concepts
before the spec hardens.

## Decisions (all approved 2026-07-14)

| Decision | Choice | Why |
|---|---|---|
| Eval linkage | Eval yaml gains required `spec.skill` | Skill + eval travel together; eval gates cheap-model trust per skill; validator checks eval→skill refs |
| Workflow migration | Convert multi-skill workflows to process skills; delete single-skill wrappers | Superpowers pattern: workflows ARE skills; 1:1 wrappers are noise |
| Rename | `agents/` → `roles/`, `kind: AgentRole` → `kind: Role` | Role = real-world abstraction (WHO); avoids "agent" overload with runtime agents; cheapest now, before adapter #2 |
| Version compat | Hard cut — only v1alpha2 accepted, targeted error for v1alpha1 | Alpha = zero compat promise; dual-version validator = permanent tax |
| Hermes commands | One command per skill | Skills are the entry points now; converted workflows keep command parity automatically |
| Command namespace | Prefix `ops` (user decision — easier to type than `aoh`) | Canonical command = `ops:<skill>`; adapters map separator to runtime convention; name conflicts are other tools' problem |

## Spec changes (v1alpha2)

- `apiVersion: openagentix.io/v1alpha2` on all kinds. Validator hard-rejects v1alpha1
  with: `v1alpha1 no longer supported — see docs/spec.md migration notes`.
- `kind: Workflow` removed. A `workflows/` dir in a pack is a validation **error**
  (stale packs fail loudly, not silently).
- `agents/` dir → `roles/`; `kind: AgentRole` → `kind: Role`. Role spec drops the
  `workflows:` field.
- Eval spec gains required `spec.skill` (single skill reference). Validator enforces
  eval→skill referential integrity.
- Process skill = plain SKILL.md that orchestrates other skills by name. No new kind,
  no frontmatter extension — documented convention only (superpowers pattern).
- Generated commands are namespaced: canonical name `ops:<skill>`. Separator is a
  per-adapter mapping (GSD precedent — prefix baked into artifact name, separator per
  surface):

  | Runtime | Surface | Command |
  |---|---|---|
  | Hermes | `commands/ops-<skill>.md` | `ops-<skill>` |
  | Claude Code | `commands/ops/<skill>.md` (subdir → namespace) | `/ops:<skill>` |
  | Codex | `prompts/ops-<skill>.md` | `/ops-<skill>` |
  | OpenCode | `command/ops-<skill>.md` | `/ops-<skill>` |

  Engine-neutral rule holds: prefix lives in spec; separator mapping lives in adapters.

## Code changes

### src/aoh/pack.py

- Delete `Pack.workflows`, `AgentRole.workflows`, and the entire workflow validation
  block in `validate_pack`.
- Rename dataclass `AgentRole` → `Role`; `Pack.agent_roles` → `Pack.roles`;
  `load_role` reads `roles/<name>.yaml` with `kind: Role`.
- apiVersion check → `openagentix.io/v1alpha2` (targeted error for v1alpha1).
- New check: `workflows/` dir present → `PackError`.
- Add `Eval` loading (`spec.skill` required, `spec.prompt`); validator checks
  eval→skill refs.

### src/aoh/adapters/hermes.py

- Commands generated per skill: `commands/ops-<skill>.md` (was per workflow).
- Drop `Workflows:` lines from SOUL.md and reference renders.
- Manifest keys: `agentRoles` → `roles`; commands list reflects per-skill files.
- `_render_workflow_reference` → `_render_pack_reference`; generated file
  `references/aoh-workflow.md` → `references/aoh-pack.md`.

### src/aoh/authoring.py

- `aoh init` template: no workflow yaml; eval carries `spec.skill`; `roles/` dir;
  apiVersion v1alpha2.

### docs/spec.md

- Rewrite for v1alpha2 + migration-notes section (v1alpha1 → v1alpha2 mapping).

## Pack migrations

| Workflow | Skills | Fate |
|---|---|---|
| docker-disk-cleanup (core) | 1 | Delete yaml; eval retargets skill |
| platform-sre-triage (acme) | 2 | → process skill `platform-sre-triage` |
| devops-release-automation (acme) | 3 | → process skill |
| mlops-training-triage (acme) | 2 | → process skill |

- Process skills carry the order/escalation logic implied by workflow description +
  role purpose (e.g. health report → disk cleanup → smallest safe action).
- Roles add their converted process skill to `skills:`; `workflows:` field removed.
- All evals gain `spec.skill`. Reconcile naming drift: workflow referenced eval
  `docker-disk-cleanup-basic` but file defines `docker-disk-cleanup` — fix during
  migration.
- All yamls bump to v1alpha2; `agents/` dirs renamed `roles/`.

## Testing (TDD, RED first per change)

1. v1alpha1 pack rejected with targeted error
2. `workflows/` dir present → rejected
3. `roles/` discovery + `kind: Role` accepted; `kind: AgentRole` rejected
4. Eval missing `spec.skill` → error; eval referencing missing skill → error
5. Pack with process skill validates (no special casing)
6. Hermes generates `commands/ops-<skill>.md` per skill
7. SOUL.md contains no workflow lines; role render intact
8. Existing 13 tests migrated to v1alpha2 fixtures
9. Integration: both packs validate; Hermes profile regen succeeds

## Out of scope

Adapter interface extraction (phase 3), drift manifest (phase 4), Binding (phase 7),
back-compat shim, `aoh migrate` command (YAGNI — only our 2 packs exist).

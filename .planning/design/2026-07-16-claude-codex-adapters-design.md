# Claude Code + Codex Adapters (+ RuntimeAdapter interface) — Design

Date: 2026-07-16. Approved in brainstorming. Delivers ROADMAP phase 3 (adapter
interface) + phase 5 (Claude Code adapter) + a new Codex adapter, porting the kubeops
read-only kubernetes agent to both. Proves the engine-neutral claim with two real
second adapters.

## Goal

Port the kubeops kubernetes agent (kubeops-copilot role + 4 read-only skills + the
sresquad RBAC binding) to Claude Code and Codex via a shared `RuntimeAdapter` interface;
enforce read-only per runtime's native guardrails plus the cluster RBAC "second wall";
validate with unit tests + a live RBAC denial proof; update the docs — including a
dedicated "two walls" explainer.

## Decisions (approved 2026-07-16)

| Decision | Choice | Why |
|---|---|---|
| Interface | Extract `RuntimeAdapter` Protocol + shared `AdapterResult`; hermes conforms; registry `{hermes, claude-code, codex}` | PROJECT.md decided "adapter interface before adapter #2"; prevents Hermes conventions ossifying |
| CLI | Add `aoh install --runtime <x> <pack> --output <dir> …`; keep old `install-hermes*`/`adapt-hermes` as aliases | Decided `aoh install --runtime <x>`; aliases keep tutorials/tests/docs working |
| Claude Code read-only | TWO walls: `settings.json` `permissions.deny` for kubectl mutations AND binding's scoped RBAC kubeconfig | Claude Code is the one runtime that expresses subcommand deny in config; RBAC is the floor |
| Codex read-only | ONE wall: scoped RBAC kubeconfig + AGENTS.md instruction + `approval_policy` note | Codex has no kubectl-subcommand deny (like Hermes); adapter documents the gap honestly |
| Output target | Self-contained workspace dir + `launch.sh` per adapter (non-invasive) | Matches Hermes' generate-not-install ethos; portable; never clobbers ~/.claude or ~/.codex |
| Validation | Unit + live workspace generation + `kubectl delete` → Forbidden via scoped kubeconfig; NO live claude/codex sessions | Sessions need interactive CLIs; RBAC proof + artifacts = validated |
| Docs | Two-walls explainer (concept page + deck slide + field note); adapters ref shipped; new Claude Code tutorial | User: the two-walls capability is strong + under-known |
| Access modes | Binding gains `spec.access: scoped \| inherit` (default scoped) | User: support inheriting system kubeconfig; scoped stays the safe-harness default |
| Multi-cluster | One binding per cluster; one workspace/profile per binding; switching = directory/profile choice | User: project-specific profiles, switchable; no global context mutation ever |

## Grounded runtime formats (verified against local installs 2026-07-16)

- **Claude Code** `settings.json`: `{ "env": {...}, "permissions": { "allow": ["Bash(cmd:*)"], "deny": [...], "defaultMode": "default" } }`. Skills: `.claude/skills/<name>/SKILL.md`. Commands: `.claude/commands/ops/<skill>.md` → `/ops:<skill>` (subdir = namespace). Agents: `.claude/agents/<name>.md` (frontmatter `name`, `description`, `tools`). Memory: `CLAUDE.md`.
- **Codex** (`codex-cli 0.143.0`): `~/.codex/config.toml` keys `model`, `model_reasoning_effort`, `approval_policy`, `[projects."<path>"]`. Custom prompts: `.codex/prompts/<name>.md` → `/<name>`. Memory: `AGENTS.md`. Approval policy values to confirm at plan time (e.g. `untrusted`/`on-failure`/`never`); sandbox_mode is filesystem-scoped (not kubectl-aware).

## Architecture

### src/aoh/adapters/base.py (new)
```python
@dataclass(frozen=True)
class AdapterResult:            # moved here from hermes.py
    runtime: str
    output_dir: Path
    generated_files: list[Path]

class RuntimeAdapter(Protocol):
    name: str
    def adapt(self, pack: Pack, output_dir: Path) -> AdapterResult: ...
    def install_agent(self, pack: Pack, output_dir: Path, *, profile: str,
                      binding: Binding | None, role_name: str | None,
                      provider: str, model: str, cwd: str) -> AdapterResult: ...

ADAPTERS: dict[str, RuntimeAdapter]   # {"hermes", "claude-code", "codex"}
```
Shared helpers reused across adapters: the read-only kubectl mutation verb list, the
`_SAFE_BINDING_VALUE_RE` guard, the provision.sh renderer (RBAC identity is
runtime-agnostic — hoist from hermes.py to base.py or a `_rbac.py`).

### src/aoh/adapters/hermes.py
Conform to the protocol (wrap existing functions; behavior unchanged). Existing 31 tests
stay green. `AdapterResult` import moves to base.

### src/aoh/adapters/claude_code.py (new) → workspace dir
```
<output>/
  .claude/skills/<skill>/SKILL.md          copied from pack (+ scripts/)
  .claude/commands/ops/<skill>.md          → /ops:<skill>
  .claude/agents/<role>.md                 role as subagent (frontmatter name/description/tools)
  .claude/settings.json                    WALL 1 + env.KUBECONFIG
  CLAUDE.md                                role, read-only posture, the two-walls note
  kubeconfig, provision.sh                 (binding) WALL 2 — scoped RBAC identity
  launch.sh                                cd + export KUBECONFIG=./kubeconfig + exec claude
```
`settings.json` (wall 1): `permissions.deny` = `Bash(kubectl delete:*)`, and the same for
`apply|edit|patch|replace|drain|cordon|scale|rollout|annotate|label|create|delete`
(and `kubectl * --kubeconfig`-agnostic — patterns match the verb); `permissions.allow` =
`Bash(kubectl get:*)`, `describe`, `logs`, `top`, `events`, `version`, `config view`,
plus the pack's skill scripts; `env.KUBECONFIG` = the workspace kubeconfig.

### src/aoh/adapters/codex.py (new) → workspace dir
```
<output>/
  AGENTS.md                                role, read-only posture, "RBAC is the wall"
  .codex/prompts/ops-<skill>.md            → /ops-<skill>
  .codex/config.toml                       model, model_reasoning_effort, approval_policy note
  kubeconfig, provision.sh                 (binding) the single wall
  launch.sh                                cd + export KUBECONFIG + exec codex
```
No subcommand deny available; AGENTS.md states the read-only contract and that the
cluster enforces it. Adapter's generated notes document the guardrail gap.

### src/aoh/cli.py
`install` subcommand: `--runtime {hermes,claude-code,codex}` (required), pack positional,
`--output` (required), `--binding`, `--role`, `--profile`, `--provider`, `--model`,
`--cwd`. Dispatch through `ADAPTERS[runtime].install_agent(...)`. Old subcommands remain,
implemented via the same adapter, printing a one-line deprecation hint.

## Access modes + multi-cluster profiles (amendment, approved 2026-07-16)

### Binding `spec.access: scoped | inherit` (default `scoped`)

```yaml
spec:
  role: kubeops-copilot
  access: scoped          # scoped (default) | inherit
  target:
    kubeContext: prod-gke
    namespace: default
```

- **scoped** — as built: provision.sh mints a dedicated SA + read-only ClusterRole →
  workspace `kubeconfig`. Separate identity, audit trail, wall #2.
- **inherit** — no cluster objects. provision.sh instead runs
  `kubectl config view --minify --flatten --context <ctx>` → workspace `kubeconfig`
  that is a **context-pinned snapshot of the user's own credentials** (namespace set).
  Zero admin needed; agent acts as the USER; wall #2 gone. Generated
  CLAUDE.md/AGENTS.md/SOUL state this explicitly. Claude Code keeps wall #1.
- Uniform mechanics: workspace always carries `./kubeconfig`; launch.sh always exports
  it; skill scripts unchanged; only provision.sh's body differs by mode.
- Never `kubectl config use-context` (mutates the user's global default — anti-pattern).
  Plain inherit-system-default rejected: agent would follow whatever context the user
  last switched to.
- Honest wall count: scoped = 2 walls (CC) / 1 (Codex, Hermes); inherit = 1 wall (CC) /
  0 (Codex, Hermes — instructions only).

### Multi-cluster = one binding per cluster, one workspace/profile per binding

Site repo carries N bindings (`kubeops-sresquad.yaml`, `kubeops-staging.yaml`,
`kubeops-prod.yaml`). One `aoh install` per binding → one workspace per cluster;
project-specific by placing the workspace inside the project dir (Claude Code is
cwd-scoped by design). **Switching clusters = choosing the workspace/profile** —
`cd <ws> && ./launch.sh`, or Hermes `--profile <name>`. No `aoh switch` command (YAGNI —
install is cheap + idempotent). Binding groups / fan-out stays phase 7.

## The two walls (docs artifact + adapter reference)

| Runtime | Wall 1 — runtime guardrail | Wall 2 — cluster RBAC | Walls |
|---|---|---|---|
| Claude Code | `settings.json` `permissions.deny` (kubectl mutations) | scoped kubeconfig | **2** |
| Codex | approval policy (coarse, not kubectl-aware) | scoped kubeconfig | 1.5 |
| Hermes | none (no kubectl awareness) | scoped kubeconfig | 1 |

Explainer thesis: most users don't know Claude Code can express *subcommand-level* deny
(`Bash(kubectl delete:*)` allowed-vs-denied) in `settings.json` — a real policy wall in
the runtime, independent of the cluster. AOH generates it from the declared
`kubectl-readonly` RuntimeRequirement, then RBAC backs it as the un-bypassable floor.

## Validation

- TDD unit per adapter: protocol conformance; workspace file set; Claude `settings.json`
  deny/allow rules correct (delete/apply/etc denied, get/describe/logs allowed);
  `env.KUBECONFIG` set; CLAUDE.md/AGENTS.md content; commands/prompts one-per-skill with
  `ops` namespace; binding → kubeconfig + provision.sh (0755) + KUBECONFIG in launch.sh;
  unsafe-binding-value rejection reused; role-defaults-from-binding + missing-role +
  kubeContext-required errors (shared with hermes); `access: inherit` → provision.sh
  contains the minify-flatten snapshot (no SA/ClusterRole), `access: scoped`/absent →
  RBAC provisioning; invalid access value rejected.
- Regression: hermes 31 tests green after refactor; both existing packs validate.
- Live: `aoh install --runtime claude-code|codex collections/core/kubeops --output … --binding examples/sresquad-site/bindings/kubeops-sresquad.yaml`; run provision.sh; `kubectl --kubeconfig <ws>/kubeconfig delete pod …` → Forbidden; `auth can-i delete pods` → no. Inspect generated settings.json / AGENTS.md.

## Docs updates

- `docs-site` concept **safe-agents**: add the two-walls section + guardrail table + a
  mermaid (runtime wall + RBAC wall → both must pass). Update "why not trust the runtime"
  to note Claude Code is the exception that *can* express subcommand deny.
- `docs-site` **reference/adapters**: flip Claude Code + Codex to shipped; add the three
  workspace layouts + the guardrail table + the `aoh install --runtime` CLI.
- `docs-site` **reference/cli**: add `aoh install --runtime`; note old subcommands aliased.
- `docs-site` **new tutorial** `tutorials/kubeops-claude-code`: generate the workspace,
  provision, show settings.json deny, the denial proof, launch note.
- `docs-site` safe-agents **deck**: +1 two-walls slide.
- `docs-site` **field note** `2026-07-16-two-walls`: the Claude Code permission most miss.
- repo `docs/spec.md` (adapters/commands), `docs/hermes-adapter.md` sibling note or a new
  `docs/adapters.md`; `CHANGELOG` Added; `.planning` STATE/ROADMAP (phases 3+5 done).

## Out of scope

Live claude/codex session automation, Goose/OpenCode adapters, non-k8s bindings,
per-skill command-content scoping, MCP wiring, drift model.

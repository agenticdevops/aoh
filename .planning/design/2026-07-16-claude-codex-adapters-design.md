# Claude Code + Codex Adapters (+ RuntimeAdapter interface) — Design v2

Date: 2026-07-16. v1 approved in brainstorming; v2 reworked after external peer review
(Codex CLI, model gpt-5.6-sol, verdict REWORK, 12 findings — all adjudicated, see
"Review adjudication" at bottom). Delivers ROADMAP phase 3 (adapter interface) +
phase 5 (Claude Code adapter) + a Codex adapter, porting the kubeops read-only
kubernetes agent to both.

## Goal

Port the kubeops kubernetes agent (kubeops-copilot role + 4 read-only skills + the
sresquad binding) to Claude Code and Codex via a shared `RuntimeAdapter` interface.
Enforce read-only with layered controls stated honestly: a hard RBAC boundary
(scoped identity) plus per-runtime best-effort guardrails. Validate with unit tests,
an `auth can-i` matrix, adversarial guardrail checks, and a live denial proof. Update
docs — including a "two walls" explainer that names what each wall is and is not.

## Decisions (v1 approved; v2 amendments marked ►)

| Decision | Choice | Why |
|---|---|---|
| Interface | `RuntimeAdapter` Protocol + registry `{hermes, claude-code, codex}` | Decided "interface before adapter #2" |
| ► Protocol shape | Single `materialize(request: MaterializeRequest) -> AdapterResult`; request carries pack, output_dir, role/team, binding, model intent, workdir; runtime-specific options validated by the adapter, not in the protocol; `AdapterResult` gains `diagnostics: list[str]` (spec.md requires adapters to warn on unenforceable requirements) | Review F8: `profile/provider/cwd` were Hermes-isms; diagnostics needed |
| CLI | New `aoh install --runtime <x>`; ► old subcommands stay as UNCHANGED compat handlers (not "aliases") — only `install-hermes-agent` reroutes through the new path, with a stderr deprecation hint | Review F9: adapt/pack/team commands are different operations |
| Claude Code read-only | ► Hard boundary = scoped RBAC kubeconfig. Best-effort runtime guardrail = `settings.json` deny + a generated `PreToolUse` hook that parses commands and rejects kubectl mutations. Guardrail is NOT called a security boundary | Review F2: `Bash()` patterns bypassable (`--context` prefix, abs path, `sh -c`); hook parses the effective command |
| Codex read-only | ► Hard boundary = scoped RBAC kubeconfig. Runtime side: `approval_policy`/`sandbox_mode` are coarse; AGENTS.md states the contract. Documented gap | Review F3/F6 |
| Output target | Self-contained workspace dir + `launch.sh`; never touches `~/.claude` / `~/.codex` | Non-invasive |
| Access modes | ► `spec.access: scoped \| inherit` (default scoped). Inherit = OVERLAY kubeconfig (no credential copy — see below) | Review F4: snapshot broke exec-plugin auth + violated "never store secrets" |
| Multi-cluster | One binding per cluster; one workspace/profile per binding; switch = directory/profile choice; never `kubectl config use-context` | v1 |
| Validation | ► Unit + `auth can-i` matrix + adversarial guardrail probes + live denial proof + live `codex exec` skill-discovery probe; claims not tested are labeled unverified | Review F12 |

## Grounded runtime formats (corrected per review F3/F6, codex-cli 0.144.x)

- **Claude Code**: `.claude/skills/<name>/SKILL.md`; commands `.claude/commands/ops/<skill>.md` → `/ops:<skill>`; agents `.claude/agents/<name>.md`; `settings.json` `{env, permissions{allow,deny,defaultMode}, hooks{PreToolUse}}`; memory `CLAUDE.md`.
- **Codex** (0.144.x): project skills `.agents/skills/<name>/SKILL.md` (custom prompts are DEPRECATED, user-global only — not used); memory `AGENTS.md` (root, nested toward CWD); project config `.codex/config.toml` (trusted projects only) with keys `model`, `model_reasoning_effort` (`minimal..xhigh`), `approval_policy` (`untrusted|on-request|never`), `sandbox_mode` (`read-only|workspace-write|danger-full-access`); kubectl needs network → `sandbox_mode = "workspace-write"` + `[sandbox_workspace_write] network_access = true`, documented as a trade-off. The `ops` namespace is kept by naming wrapper skills `ops-<skill>`.

## Architecture

### src/aoh/adapters/base.py (new)
```python
@dataclass(frozen=True)
class MaterializeRequest:
    pack: Pack
    output_dir: Path
    role_name: str | None = None
    team_name: str | None = None
    binding: Binding | None = None
    profile: str | None = None          # display/profile name where the runtime has one
    model_hint: str | None = None       # intent-level; adapter maps or ignores w/ diagnostic
    workdir: str | None = None
    options: dict[str, str] = field(default_factory=dict)  # runtime-specific, adapter-validated

@dataclass(frozen=True)
class AdapterResult:
    runtime: str
    output_dir: Path
    generated_files: list[Path]
    diagnostics: list[str] = field(default_factory=list)   # warnings: unenforceable reqs, gaps

class RuntimeAdapter(Protocol):
    name: str
    def materialize(self, request: MaterializeRequest) -> AdapterResult: ...

ADAPTERS: dict[str, RuntimeAdapter]
```
Shared in base (or `_k8s.py`): the RBAC provision renderer, the overlay renderer,
per-field validators (below), the kubectl read/mutation verb lists.

`hermes.py` conforms via a thin `materialize` that routes to the existing
`install_hermes_agent`; the existing public functions and team/pack/adapt operations
remain as-is (31 tests green). `AdapterResult` moves to base; hermes re-exports.

### Scoped RBAC — explicit allowlist (review F1; replaces `*/*` wildcard)

ClusterRole `aoh-readonly` becomes an explicit resource allowlist sized to the four
skills, get/list/watch only:
- core: `nodes`, `pods`, `pods/log`, `events`, `endpoints`, `services`,
  `persistentvolumeclaims`, `persistentvolumes`, `namespaces`,
  `replicationcontrollers`, `resourcequotas`, `limitranges`
- `apps`: `deployments`, `replicasets`, `daemonsets`, `statefulsets`
- `batch`: `jobs`, `cronjobs`
- `metrics.k8s.io`: `nodes`, `pods` (for `kubectl top`; absent server tolerated)
- `events.k8s.io`: `events`

Explicitly ABSENT: `secrets`, `configmaps`, `nodes/proxy`, `pods/exec`, `pods/attach`,
`pods/portforward`, `serviceaccounts/token`, RBAC objects, `certificatesigningrequests`.
Scope justification: the scripts strictly need fewer kinds (nodes, pods, pods/log,
events, endpoints, PVCs, deployments); the extra workload kinds (replicasets,
statefulsets, daemonsets, jobs, cronjobs, services, namespaces, quotas) are deliberate
small headroom for free-form triage BEYOND the deterministic scripts — all
non-sensitive, all read-only. Anything sensitive stays excluded.
The Hermes adapter's existing provision renderer is updated to this same allowlist
(one shared renderer). Docs' "read-only ≠ read-nothing" note becomes "and Secrets are
excluded by default".

### Threat model / walls language (review F5/F7 — replaces wall arithmetic)

| Runtime | Hard enforcement boundary | Best-effort runtime guardrail | Required assumptions |
|---|---|---|---|
| Claude Code | cluster RBAC via scoped identity | `permissions.deny` + PreToolUse hook | agent uses the workspace kubeconfig; host creds not isolated unless sandboxed |
| Codex | cluster RBAC via scoped identity | approval/sandbox policy (not kubectl-aware) | same |
| Hermes | cluster RBAC via scoped identity | none | same |

Honest statement everywhere: the scoped kubeconfig is the **default identity**, not
containment — a hostile agent could read other credentials on the host. Containment
(isolated HOME/container) is out of scope and stated as an assumption. RBAC bounds
whatever authenticates AS the scoped identity; that is the hard boundary.

### src/aoh/adapters/claude_code.py (new) → workspace dir
```
<output>/
  .claude/skills/<skill>/SKILL.md (+scripts)
  .claude/commands/ops/<skill>.md            → /ops:<skill>
  .claude/agents/<role>.md
  .claude/settings.json                      guardrail + env.KUBECONFIG
  .claude/hooks/kubectl-guard.sh             PreToolUse hook (0755)
  CLAUDE.md                                  role, posture, walls explained honestly
  kubeconfig | kubeconfig-overlay            per access mode
  provision.sh                               scoped mode only (0755)
  launch.sh                                  exports KUBECONFIG, execs claude
```
`settings.json`: `permissions.deny` covers verbs `delete, apply, edit, patch, replace,
create, drain, cordon, uncordon, taint, scale, rollout, set, annotate, label, expose,
run, debug, autoscale, exec, attach, port-forward, cp, certificate` (+ `helm upgrade/
install/uninstall/rollback`); `permissions.allow` covers `kubectl get/describe/logs/
top/events/api-resources/api-versions/explain/version/auth can-i` and the pack's skill
scripts; NO `kubectl config` in allow (`view --raw` leaks creds); `defaultMode` stays
`default` (unlisted → prompt) with the HOOK as the parser-level backstop:
`kubectl-guard.sh` receives the tool call JSON, extracts the command, normalizes
(wrappers, abs paths, `--flags` before verb), and denies any kubectl/helm invocation
whose verb is not in the read allowlist. **Fail-closed**: parse failure, missing `jq`,
malformed JSON, or ambiguous shell syntax ALL exit 2 (block) — never fall through to
allow. Verb matching is tuple-aware (`kubectl auth can-i` allowed; `kubectl auth
reconcile` blocked). Guardrail, not boundary — CLAUDE.md says so.

### src/aoh/adapters/codex.py (new) → workspace dir
```
<output>/
  .agents/skills/ops-<skill>/SKILL.md (+scripts)   wrapper-named to keep ops namespace;
                                                   frontmatter `name:` REWRITTEN to
                                                   ops-<skill> (dir rename alone does
                                                   not set the invocation name)
  AGENTS.md                                        role, posture, "RBAC is the boundary"
  .codex/config.toml                               model, approval_policy="on-request",
                                                   sandbox_mode="workspace-write",
                                                   [sandbox_workspace_write] network_access=true
  kubeconfig | kubeconfig-overlay, provision.sh    per access mode
  launch.sh                                        exports KUBECONFIG, execs codex
```
Diagnostics emitted: "Codex has no kubectl-aware guardrail; network access enabled for
kubectl; RBAC is the enforcement boundary." Config note documents the trusted-project
requirement.

### Access modes (review F4 — inherit redesigned, no credential copy)

- **scoped** (default): provision.sh → SA + allowlist ClusterRole + binding + token →
  workspace `kubeconfig` (0600). Manifest records server URL, SA name, context,
  namespace, token expiry (F11). Re-running provision.sh refreshes the token; launch.sh
  prints a warning when the recorded expiry has passed.
- **inherit**: NO snapshot, NO `--raw`, no credentials written (PROJECT.md "never
  store" holds). At materialize time the adapter RESOLVES the target context's
  cluster/user entry names from the user's merged kubeconfig via
  `kubectl config view -o jsonpath='{.contexts[?(@.name=="<ctx>")].context}'`
  (read-only, redacted view — never `--raw`), then writes `kubeconfig-overlay`: a
  minimal kubeconfig with `current-context: <ctx>` + one context entry pinning the
  RESOLVED cluster/user names + namespace. launch.sh exports
  `KUBECONFIG=<ws>/kubeconfig-overlay:${KUBECONFIG:-$HOME/.kube/config}` (kubeconfig
  merge rules: first file wins for current-context; the context's cluster/user
  references resolve against entries in the user's file; credentials stay there,
  exec-plugins like gke-gcloud-auth-plugin keep working). Materialization VERIFIES the
  overlay by running `kubectl config view --minify` under the merged KUBECONFIG and
  fails with a diagnostic if the context does not resolve. Agent acts as the USER;
  no hard boundary; CLAUDE.md/AGENTS.md/SOUL state it. Never mutates the user's file.

### Binding validation (review F10)

- `Binding` gains `access: str = "scoped"`; loader rejects values outside
  {scoped, inherit}.
- Per-field validators replace the single regex: binding name → DNS-1123 label
  (it names the SA); namespace → DNS-1123; kubeContext → printable, no shell metachars,
  ALLOWS `:/._@-` (EKS ARNs are legal contexts). All values passed to bash via
  `shlex.quote` regardless (defense independent of validation).

### CLI

`aoh install --runtime {hermes,claude-code,codex} <pack> --output <dir>
[--binding] [--role] [--profile] [--model]` → `ADAPTERS[rt].materialize(...)`.
Old subcommands: handlers unchanged; `install-hermes-agent` additionally prints a
stderr hint pointing at `aoh install --runtime hermes`.

## Validation (review F12)

- Unit (TDD): protocol conformance ×3; workspace file sets; settings.json deny/allow
  content; hook present + executable + blocks `kubectl --context x delete`,
  `/usr/bin/kubectl delete`, `sh -c 'kubectl delete …'` and passes `kubectl get`
  (hook tested directly as a script with fabricated tool-call JSON); AGENTS.md /
  config.toml contents incl. corrected keys; overlay mode writes no credentials
  (assert no `client-key-data|token:` in overlay); scoped provision contains the
  explicit allowlist and NOT `resources: ["*"]`; binding access validation; per-field
  validators (EKS ARN context accepted, uppercase SA name rejected); shlex quoting.
- Regression: hermes suite green; all packs validate; hermes provision renderer now
  emits the allowlist (its tests updated).
- Live (kind-sresquad-demo): generate both workspaces from the real pack+binding;
  provision; `kubectl auth can-i` matrix — `get pods` yes, `delete pods` no,
  `get secrets` **no**, `create pods/exec` no, `get nodes/proxy` no; delete → Forbidden;
  `codex exec` probe inside the workspace asking it to list available skills
  (verifies `.agents/skills` discovery); Claude Code guardrail exercised via the hook
  unit tests, NOT a live session — the live-session claim is explicitly out of scope
  and the docs say the hook is script-tested.

## Docs updates

Same set as v1 (safe-agents two-walls section + deck slide, adapters/cli reference,
new Claude Code tutorial, field note) with v2 language: hard-boundary vs best-effort
table replaces wall counts; Secrets now excluded by the allowlist (update the old
honesty note in safe-agents + kubeops tutorial + kubeops demo doc); inherit-mode page
section; Codex `.agents/skills` facts; deprecation hint for install-hermes-agent.

## Out of scope

Live claude/codex session automation, sandbox/container isolation of host credentials
(stated assumption), Goose/OpenCode, binding groups (phase 7), identity-change
confirmation on reprovision (follow-up), MCP wiring, drift model.

## Review adjudication (Codex gpt-5.6-sol, 12 findings)

Accepted: F1 (allowlist ClusterRole), F2 (verbs + hook + honest framing, drop `config
view` from allow), F3 (`.agents/skills` + wrapper naming), F4 (overlay instead of
snapshot), F5 (identity-not-containment language), F6 (config.toml facts), F7
(3-column table), F9 (compat handlers, not aliases), F10 (access field + per-field
validators + shlex), F12 (can-i matrix + adversarial hook tests + codex discovery
probe; untested claims labeled).
Accepted-adapted: F8 (MaterializeRequest + diagnostics adopted; full capabilities
object deferred — a `name` + request-validation suffices for 3 adapters; revisit at
Goose), F11 (manifest identity/expiry + refresh-by-rerun + launch warning adopted;
identity-change confirmation deferred as follow-up).

Convergence round (same reviewer, v2): 10/12 RESOLVED, F4/F11 PARTIAL with deferrals
judged sound. Verdict APPROVE-WITH-CHANGES; the 4 changes are folded in above:
overlay construction resolves cluster/user names via redacted `kubectl config view`
jsonpath + `--minify` verification (HIGH); PreToolUse hook specified fail-closed with
tuple-aware verb matching (MEDIUM); codex wrapper rewrites SKILL.md frontmatter `name`
(MEDIUM); RBAC allowlist scope justified (LOW). FINAL.

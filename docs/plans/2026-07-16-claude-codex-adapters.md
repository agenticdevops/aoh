# Claude Code + Codex Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** RuntimeAdapter interface + Claude Code and Codex adapters porting the kubeops read-only agent, with layered guardrails (RBAC allowlist hard boundary; per-runtime best-effort guardrails), `access: scoped|inherit` binding modes, `aoh install --runtime`, full validation, docs.

**Architecture:** Spec (authoritative, 3 review rounds final): `.planning/design/2026-07-16-claude-codex-adapters-design.md`. New `adapters/base.py` (protocol + registry) and `adapters/_k8s.py` (shared RBAC/overlay renderers + validators). `hermes.py` conforms unchanged in behavior. New `claude_code.py`, `codex.py`. `pack.py` Binding gains `access`.

**Tech Stack:** Python 3 + uv, pytest; generated bash/JSON/TOML; kind cluster `kind-sresquad-demo` for live proof; codex-cli 0.144.5 for execpolicy proofs.

## Global Constraints

- Tests: `rtk proxy uv run pytest -q` (this exact form). Baseline 31 passing.
- Validate packs: `uv run aoh validate <pack>` (one per invocation).
- TDD RED→GREEN→commit per task. Engine-neutral: no runtime concepts in `pack.py` (the `access` enum is spec-level, not runtime-specific).
- Grounded runtime facts are IN THE SPEC — transcribe, do not re-research: Claude `.claude/{skills,commands/ops,agents,settings.json,hooks}`; Codex `.agents/skills/ops-<skill>/`, `AGENTS.md`, `.codex/config.toml`, `.codex/rules/*.rules`; Codex PreToolUse CANNOT block.
- Honest language everywhere: RBAC = hard boundary; deny/hook/rules = best-effort guardrail; never "un-bypassable" for anything except "RBAC bounds the scoped identity".
- All generated bash interpolations go through `shlex.quote`.
- Author attribution on commits: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: base protocol, shared k8s renderers, Binding.access, hermes conformance

**Files:**
- Create: `src/aoh/adapters/base.py`, `src/aoh/adapters/_k8s.py`
- Modify: `src/aoh/adapters/hermes.py`, `src/aoh/pack.py`
- Test: `tests/test_adapter_base.py` (new), `tests/test_binding.py` (extend/adjust)

**Interfaces (produced — Tasks 2-4 depend on these exact names):**
```python
# base.py
@dataclass(frozen=True)
class MaterializeRequest:
    pack: Pack
    output_dir: Path
    role_name: str | None = None
    binding: Binding | None = None
    profile: str | None = None
    model_hint: str | None = None
    workdir: str | None = None
    options: dict[str, str] = field(default_factory=dict)

@dataclass(frozen=True)
class AdapterResult:
    runtime: str
    output_dir: Path
    generated_files: list[Path]
    diagnostics: list[str] = field(default_factory=list)

class RuntimeAdapter(Protocol):
    name: str
    def materialize(self, request: MaterializeRequest) -> AdapterResult: ...

ADAPTERS: dict[str, RuntimeAdapter]  # populated: hermes (this task), claude-code (T2), codex (T3)
```
```python
# _k8s.py — shared, runtime-agnostic
READONLY_VERBS = ("get", "list", "watch")
KUBECTL_READ_COMMANDS = ("get", "describe", "logs", "top", "events", "explain",
                         "api-resources", "api-versions", "version", "auth can-i")
KUBECTL_MUTATION_COMMANDS = ("delete", "apply", "edit", "patch", "replace", "create",
    "drain", "cordon", "uncordon", "taint", "scale", "rollout", "set", "annotate",
    "label", "expose", "run", "debug", "autoscale", "exec", "attach", "port-forward",
    "cp", "certificate")
def validate_binding_fields(binding: Binding) -> None   # per-field; PackError on bad
def render_provision_script(binding: Binding) -> str    # scoped mode; allowlist RBAC
def render_overlay_note() ...                            # (T5 adds overlay fns)
```
- Binding gains `access: str = "scoped"`; `load_binding` validates `access in {"scoped","inherit"}` else PackError "Binding `X` spec.access must be scoped or inherit".
- Per-field validators (replace single-regex use in hermes): binding name + namespace → DNS-1123 label `^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$`; kubeContext → `^[A-Za-z0-9][A-Za-z0-9:/._@-]*$` (EKS ARNs legal), reject shell metachars implicitly by the charset. Errors keep the existing "unsafe characters" phrasing for context, and say "must be a DNS-1123 label" for name/namespace.
- Allowlist ClusterRole replaces `*/*` in the provision renderer (BOTH hermes + new adapters use `_k8s.render_provision_script`):

```yaml
rules:
  - apiGroups: [""]
    resources: ["nodes", "pods", "pods/log", "events", "endpoints", "services",
                "persistentvolumeclaims", "persistentvolumes", "namespaces",
                "replicationcontrollers", "resourcequotas", "limitranges"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "daemonsets", "statefulsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["metrics.k8s.io"]
    resources: ["nodes", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["events.k8s.io"]
    resources: ["events"]
    verbs: ["get", "list", "watch"]
```
  All shell values via `shlex.quote`. Everything else in the provision script (SA,
  ClusterRoleBinding `aoh-readonly-<sa>`, token 720h, kubeconfig write chmod 600,
  inline-CA check) stays as today. Manifest addition (T2/T3 write it; hermes too):
  record `server`, `serviceAccount`, `context`, `namespace`, `tokenExpiresAt`
  (ISO, computed `date -u -v+720H` fallback `date -u -d "+720 hours"`) — computed in
  the SCRIPT and appended to `<ws>/aoh-provision.json` when provision runs.
- hermes.py: `AdapterResult` moves to base (hermes re-exports for compat: `from aoh.adapters.base import AdapterResult`); `_render_provision_script` deleted in favor of `_k8s.render_provision_script`; `_SAFE_BINDING_VALUE_RE` block replaced by `validate_binding_fields(binding)`; add module-level `class HermesAdapter` with `name="hermes"` and `materialize(request)` calling `install_hermes_agent(...)` mapping fields (`profile=request.profile or request.binding.name or pack.name`, provider/model from `request.options.get("provider","openai-codex")` / `request.model_hint or "gpt-5.4"`, `cwd=request.workdir or str(Path.cwd())`); register in `ADAPTERS`.

- [ ] **Step 1 RED:** `tests/test_adapter_base.py` — tests: `ADAPTERS` contains "hermes"; `HermesAdapter.materialize` with kubeops pack + tmp binding produces the same profile files as `install_hermes_agent` (config.yaml/SOUL.md/launch.sh/provision.sh); `AdapterResult` has `diagnostics == []`; provision script contains `resources: ["nodes"` (allowlist) and NOT `resources: ["*"]` and NOT `secrets`; binding with `access: inherit` loads with `binding.access == "inherit"`; `access: bogus` → PackError; EKS-style context `arn:aws:eks:us-east-1:123:cluster/x` ACCEPTED by validators; SA name `Bad_Name` REJECTED. Write with the existing test-file header/style. Run → fails (imports missing).
- [ ] **Step 2 GREEN:** implement base.py, _k8s.py, pack.py access field, hermes changes. Existing tests that asserted the old wildcard provision content must be updated (test_binding.py's materialization test asserts `'"get", "list", "watch"'` — still passes; add assert `'secrets' not in provision_text`).
- [ ] **Step 3:** full suite green (expect ~38-40), both packs validate, commit `feat: RuntimeAdapter protocol + shared k8s renderers; RBAC allowlist; Binding.access`.

---

### Task 2: Claude Code adapter

**Files:** Create `src/aoh/adapters/claude_code.py`; Test `tests/test_claude_code_adapter.py`.

**Produces:** `ClaudeCodeAdapter` (name `claude-code`) registered in `ADAPTERS`. Workspace per spec §claude_code. Consumes T1 shared pieces.

Key renders (exact content in spec — follow it):
- `.claude/settings.json`:
```json
{
  "env": {"KUBECONFIG": "<abs workspace>/kubeconfig"},
  "permissions": {
    "deny": ["Bash(kubectl delete:*)", ... one per KUBECTL_MUTATION_COMMANDS ..., "Bash(helm install:*)", "Bash(helm upgrade:*)", "Bash(helm uninstall:*)", "Bash(helm rollback:*)"],
    "allow": ["Bash(kubectl get:*)", ... one per KUBECTL_READ_COMMANDS ..., "Bash(./.claude/skills/*)"],
    "defaultMode": "default"
  },
  "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "<abs workspace>/.claude/hooks/kubectl-guard.sh"}]}]}
}
```
  (NO `kubectl config` in allow. For inherit mode env.KUBECONFIG uses the merge path — T5.)
- `.claude/hooks/kubectl-guard.sh` (0755) — FAIL-CLOSED bash: reads stdin JSON; extracts `.tool_input.command` with jq; jq missing/parse error/empty → exit 2; normalize: strip leading `sudo|env|time`, resolve wrapper `sh|bash -c '...'` (re-extract inner), strip abs path prefixes on kubectl/helm token; if first token not kubectl/helm → exit 0 (not ours); tokenize args skipping `--flag[=v]`/`-n v`/`--context v` pairs to find the VERB tuple; verb (+subverb for `auth`) in read list → exit 0; anything else kubectl/helm → echo reason to stderr, exit 2. Ambiguity (pipes/substitution containing kubectl) → exit 2.
- `.claude/agents/<role>.md` — frontmatter `name`, `description` (role purpose), body = responsibilities + read-only contract.
- `.claude/commands/ops/<skill>.md` — same content pattern as hermes `_render_command`.
- `CLAUDE.md` — role, purpose, skills, the honest walls paragraph (hard boundary vs guardrail), binding block (cluster/ns/access mode).
- `launch.sh` — `#!/usr/bin/env bash`, `cd` to workspace, `export KUBECONFIG=...` (scoped: `$DIR/kubeconfig`), `exec claude`.
- Skills copied to `.claude/skills/` verbatim. Binding: reuse T1 provisioning (scoped). Diagnostics: none beyond binding notes.

- [ ] **Step 1 RED:** tests — workspace file set exists; settings.json parses, deny contains `Bash(kubectl delete:*)` and all mutation verbs, allow lacks any `kubectl config`, hooks block wired; hook script executable; HOOK BEHAVIOR tests by invoking the script with fabricated stdin JSON: blocks `kubectl --context prod delete pod x`, `/usr/bin/kubectl delete pod x`, `sh -c "kubectl delete pod x"`, `kubectl auth reconcile`; allows `kubectl get pods -A`, `kubectl auth can-i delete pods`; exit 2 on garbage stdin; CLAUDE.md carries "hard enforcement boundary"; agents file per role; commands one per skill.
- [ ] **Step 2 GREEN**, suite green, commit `feat: claude-code adapter — workspace, settings deny, fail-closed kubectl guard hook`.

---

### Task 3: Codex adapter

**Files:** Create `src/aoh/adapters/codex.py`; Test `tests/test_codex_adapter.py`.

**Produces:** `CodexAdapter` (name `codex`). Workspace per spec §codex:
- `.agents/skills/ops-<skill>/SKILL.md` — copied then frontmatter `name:` REWRITTEN to `ops-<skill>` (parse frontmatter, replace name line, keep description; scripts copied alongside).
- `AGENTS.md` — role, purpose, skills list (`$ops-<skill>` invocation), read-only contract, honest boundary language ("cluster RBAC is the enforcement boundary; the rules file is best-effort").
- `.codex/config.toml`:
```toml
model = "<model_hint or gpt-5.4>"
model_reasoning_effort = "medium"
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
network_access = true
```
- `.codex/rules/kubectl-readonly.rules` — header comment listing the three verified bypass gaps (--context-first, absolute path, shell wrappers) + one `forbidden` rule per mutation verb for kubectl and helm mutation commands, `allow` for read commands. Use the execpolicy rules syntax verified via `codex execpolicy check --help` at implementation time (the implementer MUST check the local syntax with `codex execpolicy check` against a scratch rules file BEFORE finalizing the renderer, and encode the working syntax; record the verified example invocation + output in the test file docstring).
- `launch.sh` — cd, export KUBECONFIG, `exec codex`.
- Binding: shared provisioning. Diagnostics (exact strings from spec §codex).

- [ ] **Step 1 RED:** tests — file set; AGENTS.md content; config.toml keys exact; every `.agents/skills/ops-*/SKILL.md` frontmatter name == dir name; rules file exists with `forbidden` + gap header; diagnostics list non-empty and mentions "best-effort"; no `.codex/prompts` anywhere.
- [ ] **Step 2 GREEN** + a LIVE syntax check: `codex execpolicy check --rules <generated>.rules -- kubectl delete pod x` → forbidden; `-- kubectl get pods` → allow (exact CLI args per `codex execpolicy check --help`; capture output into `planning/`? No — into the test as a skipped-if-no-codex integration test `@pytest.mark.skipif(shutil.which("codex") is None, ...)` using plain skipif via try/except since repo has no pytest.mark conventions — follow existing style: a test that returns early with a print when codex is absent).
- [ ] **Step 3:** suite green, commit `feat: codex adapter — .agents/skills, AGENTS.md, execpolicy rules guardrail`.

---

### Task 4: unified CLI `aoh install --runtime`

**Files:** Modify `src/aoh/cli.py`; Test extend `tests/test_cli.py`.

- New subparser `install`: positional `pack`; `--runtime` required choices `hermes|claude-code|codex`; `--output` required Path; `--binding` Path; `--role`; `--profile`; `--model`. Handler: `validate_pack`; `binding = load_binding(...) if given`; build `MaterializeRequest(pack=pack, output_dir=args.output, role_name=args.role, binding=binding, profile=args.profile, model_hint=args.model)`; `result = ADAPTERS[args.runtime].materialize(req)`; print `installed {runtime} workspace in {dir}` + each diagnostic on stderr prefixed `warning: `.
- `install-hermes-agent`: behavior unchanged, plus one stderr line `hint: prefer 'aoh install --runtime hermes'`. Other legacy commands untouched.

- [ ] **Step 1 RED:** CLI tests — `install --runtime claude-code` on kubeops + tmp binding creates `.claude/settings.json`; `--runtime codex` creates `AGENTS.md`; `--runtime hermes` creates `SOUL.md`; unknown runtime → argparse error (exit 2); diagnostics printed to stderr for codex (capsys).
- [ ] **Step 2 GREEN**, suite green, both packs validate, commit `feat: aoh install --runtime <x> unified entrypoint`.

---

### Task 5: `access: inherit` overlay mode (all three adapters)

**Files:** Modify `src/aoh/adapters/_k8s.py` (+ small hooks in each adapter); Test `tests/test_inherit_mode.py`.

- `_k8s.render_overlay_prepare_script(binding) -> str` — generated `prepare-overlay.sh` (0755): resolves the context's cluster/user names via `kubectl config view -o jsonpath=...` (NEVER `--raw`), writes `kubeconfig-overlay` (current-context + context entry with resolved names + namespace), then VERIFIES `KUBECONFIG="$OUT:$SRC" kubectl config view --minify` resolves, else exits 1 with a clear error. No credentials ever written (script greps its own output for `client-key-data\|token:` and fails if found — self-check).
- launch.sh in inherit mode exports `KUBECONFIG="$DIR/kubeconfig-overlay:${KUBECONFIG:-$HOME/.kube/config}"`.
- Adapters branch on `binding.access`: scoped → provision.sh; inherit → prepare-overlay.sh, and CLAUDE.md/AGENTS.md/SOUL binding block says "acting as YOUR credentials — no hard boundary in this mode". Claude settings env.KUBECONFIG uses the merge path. Diagnostics add the inherit warning.

- [ ] **Step 1 RED:** tests — inherit binding produces `prepare-overlay.sh` not `provision.sh`; overlay script contains no `--raw`; contains the self-check; launch.sh has the merge KUBECONFIG; scoped still produces provision.sh; SOUL/CLAUDE/AGENTS text distinguishes modes.
- [ ] **Step 2 GREEN**, suite green, commit `feat: binding access=inherit — credential-free kubeconfig overlay mode`.

---

### Task 6: live validation on kind-sresquad-demo (evidence captured)

**Files:** Create `docs/demos/adapter-validation-2026-07-16.md` (evidence doc).

Run for real (cluster consented; provisioning idempotent):
1. `uv run aoh install --runtime claude-code collections/core/kubeops --output /tmp/aoh-cc-ws --binding examples/sresquad-site/bindings/kubeops-sresquad.yaml`
2. Same for codex → `/tmp/aoh-codex-ws`.
3. Run one workspace's `provision.sh` (updates ClusterRole to the allowlist — expected: `configured`).
4. `auth can-i` matrix with the scoped kubeconfig: `get pods` yes; `delete pods` no; `get secrets` NO (this flips from the old wildcard — the headline); `create pods/exec` no; `get nodes/proxy` no. Then a real `kubectl delete pod -n kube-system <pod>` → Forbidden.
5. Re-verify the 4 skill scripts still function under the allowlist: run each `collections/core/kubeops/skills/*/scripts/*.sh` with the scoped KUBECONFIG — all succeed (no Forbidden inside).
6. `codex execpolicy check` proofs against the generated rules: delete→forbidden, get→allow, and the 3 gap forms → no-match (paste outputs).
7. `codex exec` probe in the codex workspace: "List the skills available to you" → response names ops-* skills (paste). Skip gracefully if codex auth unavailable; mark unverified.
8. Hook proof: run `.claude/hooks/kubectl-guard.sh` with the adversarial JSON samples (same as unit tests, but paste real outputs).
Paste all real outputs into the evidence doc. Update `docs/demos/kubeops-readonly.md`: the Secrets honesty note becomes "Secrets are excluded by the allowlist" + `auth can-i get secrets → no` line. Commit `docs: live adapter validation evidence — allowlist RBAC, execpolicy, hook proofs`.

---

### Task 7: repo docs + planning

**Files:** Modify `docs/spec.md` (Commands table: Claude Code + Codex rows now shipped, Codex surface `.agents/skills` + `$ops-<skill>` — correct the old `prompts/` row; Binding bullet gains `access`), Create `docs/adapters.md` (the three workspace layouts + threat table + guardrail mapping, mirroring spec §), Modify `CHANGELOG.md` (Added: adapters, protocol, install --runtime, access modes, allowlist; Changed: ClusterRole aoh-readonly narrowed — BREAKING for re-provisioned identities), `.planning/STATE.md` (session log + Position → phases 3+5 done), `.planning/ROADMAP.md` (phase 3 ✅, phase 5 ✅ + codex bonus), `.planning/PROJECT.md` decisions (adapter protocol shape; access modes; guardrail honesty language; cross-AI review loop used).
- [ ] Verify suite + validate all 3 packs; commit `docs: spec/adapters/changelog/planning — adapters shipped`.

---

### Task 8: docs-site updates

**Files (docs-site/):** `docs/concepts/safe-agents.mdx` (two-walls section w/ 3-column threat table + mermaid: command → runtime guardrail → RBAC → API server; Claude Code called out as the runtime with a config-expressible subcommand deny most users don't know); `static/decks/safe-agents.html` (+1 slide: two walls diagram); `docs/reference/adapters.md` (flip Claude Code + Codex to shipped, workspace layouts, threat table, honest gaps); `docs/reference/cli.md` (add `install --runtime`, note the hint on install-hermes-agent; un-mark claude-code/codex "(planned)" in the separator table, fix Codex row to `$ops-<skill>` skills); NEW `docs/tutorials/kubeops-claude-code.mdx` (generate workspace → provision → show settings.json deny + hook → can-i matrix incl. secrets NO → launch note; Quiz 4-6 Q, ≥1 multiSelect, all options explained); update `docs/tutorials/kubeops-readonly.mdx` Secrets note (now excluded); NEW field note `blog/2026-07-16-two-walls.md` (voice: first-person concise, "the Claude Code permission wall most people miss + why the cluster still gets the last word", truncate marker, tags [kubernetes, safety]); sidebar entry for the new tutorial.
- Grounding: everything traces to the spec + Task 6 evidence doc + generated artifacts. Build gate `npm --prefix docs-site run build` exit 0.
- [ ] Build green, commit `docs(site): two walls explainer, claude-code tutorial, adapters shipped, field note`. Push is a SEPARATE user decision — do not push.

## Self-review notes

- Spec coverage: protocol ✓(T1) allowlist ✓(T1) claude ✓(T2) codex+rules ✓(T3) CLI ✓(T4) inherit ✓(T5) validation ✓(T6) docs ✓(T7-8). Deferred per spec: capabilities object, identity-change gate, live claude session.
- Execpolicy rules syntax deliberately verified-at-implementation (T3) because the local CLI is the oracle; the plan mandates recording the verified invocation.
- Test-count expectations are approximate (~38-40 after T1) — each task's gate is "suite green", not a hardcoded number, except the T1 RED list.

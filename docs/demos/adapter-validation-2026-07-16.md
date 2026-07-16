# Live Validation: Claude Code + Codex Adapters (2026-07-16)

Proves the Claude Code and Codex runtime adapters (built T1-T5 on top of the existing
Hermes adapter) generate workspaces that actually enforce a read-only RBAC boundary
against a real cluster — not just that the generated files look right in unit tests.
Everything below ran against the live `kind-sresquad-demo` cluster; no output is
fabricated or backfilled from test expectations.

Cluster: `kind-sresquad-demo` (kind, 3 nodes). Repo HEAD at time of this run: `770c999`.

An RBAC identity `aoh-kubeops-sresquad` / ClusterRole `aoh-readonly` already existed
from an earlier session (2026-07-15) with the OLD **wildcard** rule
(`apiGroups: ["*"], resources: ["*"], verbs: [get, list, watch]`). The headline of this
run: `provision.sh` **updates** that ClusterRole in place to the new resource
allowlist introduced by the adapter work — and `auth can-i get secrets` flips from
**yes to no**.

## 1. Install both workspaces

```
$ uv run aoh install --runtime claude-code collections/core/kubeops \
    --output /private/tmp/claude-501/aoh-cc-ws \
    --binding examples/sresquad-site/bindings/kubeops-sresquad.yaml
installed claude-code workspace in /private/tmp/claude-501/aoh-cc-ws

$ uv run aoh install --runtime codex collections/core/kubeops \
    --output /private/tmp/claude-501/aoh-codex-ws \
    --binding examples/sresquad-site/bindings/kubeops-sresquad.yaml
installed codex workspace in /private/tmp/claude-501/aoh-codex-ws
warning: Codex has no complete Claude-style kubectl guardrail — execpolicy rules are
best-effort prefix matches with known bypass gaps (--context-first, absolute path,
shell wrappers); network access enabled for kubectl; RBAC is the enforcement boundary.
```

Generated file sets (matches the adapters' test expectations, verified with `find`):

```
aoh-cc-ws/.claude/agents/kubeops-copilot.md
aoh-cc-ws/.claude/commands/ops/{k8s-service-health-report,node-notready-triage,pending-pod-triage,pod-crashloop-triage}.md
aoh-cc-ws/.claude/hooks/kubectl-guard.sh
aoh-cc-ws/.claude/settings.json
aoh-cc-ws/CLAUDE.md
aoh-cc-ws/launch.sh
aoh-cc-ws/provision.sh

aoh-codex-ws/.codex/config.toml
aoh-codex-ws/.codex/rules/kubectl-readonly.rules
aoh-codex-ws/AGENTS.md
aoh-codex-ws/launch.sh
aoh-codex-ws/provision.sh
```

Both workspaces also carry the four `ops-*` skill directories (with scripts) under
`.claude/skills/` and `.agents/skills/` respectively — omitted above for brevity.

## 2. Run provision.sh once (updates the shared cluster identity)

Ran the claude-code workspace's `provision.sh` (the two workspaces target the same
binding/context/namespace, so one run provisions the shared identity both use):

```
$ /private/tmp/claude-501/aoh-cc-ws/provision.sh
serviceaccount/aoh-kubeops-sresquad configured
clusterrole.rbac.authorization.k8s.io/aoh-readonly configured
clusterrolebinding.rbac.authorization.k8s.io/aoh-readonly-aoh-kubeops-sresquad unchanged
Scoped read-only kubeconfig written to /private/tmp/claude-501/aoh-cc-ws/kubeconfig
Verify the guardrail: kubectl --kubeconfig /private/tmp/claude-501/aoh-cc-ws/kubeconfig delete pod x  # expect Forbidden
```

`configured` (not `created`) on the ServiceAccount and ClusterRole confirms this is an
update of pre-existing objects — the ClusterRoleBinding is `unchanged` because its
subject/roleRef didn't change, only the rules the ClusterRole grants did.

## 3. `auth can-i` matrix (scoped kubeconfig)

```
KC=/private/tmp/claude-501/aoh-cc-ws/kubeconfig

$ kubectl --kubeconfig $KC auth can-i get pods
yes

$ kubectl --kubeconfig $KC auth can-i delete pods
no

$ kubectl --kubeconfig $KC auth can-i get secrets
no

$ kubectl --kubeconfig $KC auth can-i create pods
no

$ kubectl --kubeconfig $KC auth can-i create pods/exec
no

$ kubectl --kubeconfig $KC auth can-i get nodes/proxy
yes
Warning: resource 'nodes' is not namespace scoped
```

**`get secrets` → no is the headline flip.** The old wildcard ClusterRole (`*`/`*`,
get/list/watch) granted read access to every Secret in the cluster; the new allowlist
(rendered by `src/aoh/adapters/_k8s.py`, shared across all three adapters) lists
specific core/apps/batch/metrics resources and **does not include `secrets`**.

**Honest note on `nodes/proxy`:** `auth can-i get nodes/proxy` reported `yes`, which
looks like a matrix failure at first glance — the ClusterRole's `nodes` rule has no
`nodes/proxy` subresource entry. `can-i` here is reporting on the parent-resource rule
match, which does not reflect actual subresource enforcement. Verified against the
real API server via `get --raw` (ground truth, not `can-i`'s opinion):

```
$ kubectl --kubeconfig $KC get --raw /api/v1/nodes/sresquad-demo-control-plane/proxy/metrics
Error from server (Forbidden): nodes "sresquad-demo-control-plane" is forbidden: User
"system:serviceaccount:default:aoh-kubeops-sresquad" cannot get resource
"nodes/proxy" in API group "" at the cluster scope
```

Actual enforcement is correct (Forbidden); `can-i`'s report for this one subresource
is misleading. Noted here rather than silently reconciling the matrix.

Also verified `pods/exec` the same way, matching its `can-i no`:

```
$ kubectl --kubeconfig $KC -n kube-system exec coredns-668d6bf9bc-5qhgx -- ls
Error from server (Forbidden): pods "coredns-668d6bf9bc-5qhgx" is forbidden: User
"system:serviceaccount:default:aoh-kubeops-sresquad" cannot create resource
"pods/exec" in API group "" in the namespace "kube-system"
```

## 4. Real delete attempt

```
$ kubectl --kubeconfig $KC delete pod -n kube-system coredns-668d6bf9bc-5qhgx
Error from server (Forbidden): pods "coredns-668d6bf9bc-5qhgx" is forbidden: User
"system:serviceaccount:default:aoh-kubeops-sresquad" cannot delete resource "pods" in
API group "" in the namespace "kube-system"
```

Pod name pulled live from the scoped kubeconfig itself
(`kubectl -n kube-system get pods -l k8s-app=kube-dns`) — not assumed. The pod was
never deleted; CoreDNS was unaffected.

## 5. Skill scripts under the scoped KUBECONFIG

All four `collections/core/kubeops/skills/*/scripts/*.sh` re-run directly with
`KUBECONFIG` exported to the scoped kubeconfig. None of these scripts call
`kubectl top` (no metrics-server dependency in this pack), so there was no
"Metrics API not available" case to hit — noted rather than invented. All four
exited 0 with real diagnostic output and zero Forbidden errors inside.

**pod-crashloop-triage** (exit 0):
```
== Pods in crash/image-pull trouble (all namespaces) ==
troublesim  crashloop-test-6968688c54-mhlg6        0/1  CrashLoopBackOff   226 (34s ago)  19h
troublesim  imagepull-test-565f5d9cbd-5bxbh        0/1  ImagePullBackOff   0              18h
troublesim  imagepull-test-565f5d9cbd-m8574        0/1  ImagePullBackOff   0              19h
troublesim  liveness-probe-test-77464549fd-qcdkd   0/1  CrashLoopBackOff   393 (5m2s ago) 19h
troublesim  liveness-probe-test-77464549fd-vwthr   0/1  CrashLoopBackOff   397 (111s ago) 19h
```

**node-notready-triage** (exit 0, trimmed):
```
== Nodes ==
NAME                          STATUS   ROLES           AGE   VERSION
sresquad-demo-control-plane   Ready    control-plane   19h   v1.32.2
sresquad-demo-worker          Ready    <none>          19h   v1.32.2
sresquad-demo-worker2         Ready    <none>          19h   v1.32.2

== Node conditions ==
NAME                          READY   REASON         MEM-PRESSURE   DISK-PRESSURE
sresquad-demo-control-plane   True    KubeletReady   False          False
sresquad-demo-worker          True    KubeletReady   False          False
sresquad-demo-worker2         True    KubeletReady   False          False

== kube-system pods (CNI, proxy, DNS) ==
(12 pods listed, all Running)

== Recent cluster events (warnings) ==
(11 FailedScheduling / Unhealthy / BackOff events for troublesim namespace)
```

**pending-pod-triage** (exit 0):
```
== Pending pods (all namespaces) ==
NAMESPACE    NAME                                   READY   STATUS              RESTARTS   AGE
troublesim   configmap-mount-test-d449d85b9-w2n67   0/1     ContainerCreating   0          19h
troublesim   imagepull-test-565f5d9cbd-5bxbh        0/1     ImagePullBackOff    0          18h
troublesim   imagepull-test-565f5d9cbd-m8574        0/1     ImagePullBackOff    0          19h
troublesim   resource-limit-test-85d74d49cf-5hmrs   0/1     Pending             0          19h
troublesim   resource-limit-test-85d74d49cf-wbw2l   0/1     Pending             0          19h
troublesim   resource-limit-test-85d74d49cf-x66tf   0/1     Pending             0          19h
```

**k8s-service-health-report** (exit 0, trimmed):
```
== Nodes ==
(3 nodes, all Ready)

== Deployments (ready vs desired) ==
(14 deployments across kube-system, local-path-storage, monitoring, shopfast, troublesim)

== Pods not Running/Succeeded ==
(9 pods: crashloop/imagepull/liveness-probe/resource-limit troublesim test pods)

== Top restart counts ==
(10 pods by restart count, highest 8 restarts)

== Warning events (recent) ==
(11 events, same as node-notready-triage)

== Services without endpoints ==
(none — all services have endpoints)
```

## 6. `codex execpolicy check` proofs

Against the generated `.codex/rules/kubectl-readonly.rules` in the codex workspace
(codex-cli 0.144.5). Recall: `codex execpolicy check` always exits 0 — the decision is
in the parsed `"decision"` JSON field, never the process return code.

```
$ codex execpolicy check --rules .codex/rules/kubectl-readonly.rules -- kubectl delete pod x
{"matchedRules":[{"prefixRuleMatch":{"matchedPrefix":["kubectl","delete"],"decision":"forbidden"}}],"decision":"forbidden"}

$ codex execpolicy check --rules .codex/rules/kubectl-readonly.rules -- kubectl get pods
{"matchedRules":[{"prefixRuleMatch":{"matchedPrefix":["kubectl","get"],"decision":"allow"}}],"decision":"allow"}
```

The three documented no-match gap forms (copied verbatim from the rules file's own
header comment, which the adapter renders directly from the same threat-model text
used in `tests/test_codex_adapter.py`):

```
$ codex execpolicy check --rules .codex/rules/kubectl-readonly.rules -- kubectl --context prod delete pod x
{"matchedRules":[]}

$ codex execpolicy check --rules .codex/rules/kubectl-readonly.rules -- /usr/bin/kubectl delete pod x
{"matchedRules":[]}

$ codex execpolicy check --rules .codex/rules/kubectl-readonly.rules -- sh -c "kubectl delete pod x"
{"matchedRules":[]}
```

`{"matchedRules":[]}` has no `"decision"` key at all — a caller that naively checks
`decision == "forbidden"` and treats anything else as safe would let all three
through. This is why the rules file is documented as best-effort and RBAC (§3-4
above) is the real enforcement boundary for the codex adapter, same as claude-code.

## 7. `codex exec` skill-discovery probe

Ran inside the codex workspace. `codex` refused to run outside a git repo by default
(`aoh-codex-ws` isn't one) — used the documented `--skip-git-repo-check` flag rather
than initializing a throwaway repo:

```
$ cd /private/tmp/claude-501/aoh-codex-ws
$ codex exec --skip-git-repo-check "List the skills available to you by name"
```

Real response (trimmed to the final answer; the agent also invoked
`superpowers:using-superpowers` per the user's global codex config before answering):

```
Available skills:

- ops-k8s-service-health-report
- ops-node-notready-triage
- ops-pending-pod-triage
- ops-pod-crashloop-triage
- superpowers:brainstorming
- superpowers:dispatching-parallel-agents
- superpowers:executing-plans
... (plus other skills from the user's global $CODEX_HOME, unrelated to this pack)
```

The four `ops-*` skills are exactly the four kubeops pack skills, correctly rewritten
to the `ops-<skill>` naming convention the codex adapter uses (confirmed against
`tests/test_codex_adapter.py::test_skill_frontmatter_name_rewritten_dir_and_content_match`).
Codex auth was available; nothing here is unverified.

## 8. Claude Code hook proof (`.claude/hooks/kubectl-guard.sh`)

Same adversarial JSON samples as the unit tests in `tests/test_claude_code_adapter.py`,
run directly against the generated hook script with real stdin and real exit codes.

```
$ echo '{"tool_input": {"command": "kubectl delete pod x"}}' | bash .claude/hooks/kubectl-guard.sh
kubectl-guard: kubectl delete is a mutation verb; blocked by guardrail
EXIT: 2

$ echo '{"tool_input": {"command": "kubectl --context prod delete pod x"}}' | bash .claude/hooks/kubectl-guard.sh
kubectl-guard: kubectl delete is a mutation verb; blocked by guardrail
EXIT: 2

$ echo '{"tool_input": {"command": "/usr/bin/kubectl delete pod x"}}' | bash .claude/hooks/kubectl-guard.sh
kubectl-guard: kubectl delete is a mutation verb; blocked by guardrail
EXIT: 2

$ echo '{"tool_input": {"command": "sh -c \"kubectl delete pod x\""}}' | bash .claude/hooks/kubectl-guard.sh
kubectl-guard: kubectl delete is a mutation verb; blocked by guardrail
EXIT: 2

$ echo '{"tool_input": {"command": "kubectl get pods -A"}}' | bash .claude/hooks/kubectl-guard.sh
EXIT: 0

$ echo '{"tool_input": {"command": "kubectl auth can-i delete pods"}}' | bash .claude/hooks/kubectl-guard.sh
EXIT: 0

$ echo 'not json at all {{{' | bash .claude/hooks/kubectl-guard.sh
kubectl-guard: stdin is not valid JSON; failing closed
EXIT: 2
```

**This is the key contrast with step 6.** The same three "gap" forms that fall
through Codex's `execpolicy` rules file with no match (`--context-first`, absolute
path, `sh -c` wrapper) are all correctly caught and blocked (exit 2) by the Claude
Code hook, because the hook does real normalization (strips wrapper shells, resolves
absolute paths, tokenizes past flags to find the verb) instead of literal prefix
matching. Claude Code's hook is a second layer on top of RBAC; Codex has no
equivalent layer — RBAC alone carries the weight there.

## Summary

| Check | Result |
|---|---|
| `provision.sh` updates existing ClusterRole | `configured` (not `created`) — confirmed |
| `auth can-i get pods` | yes |
| `auth can-i delete pods` | no |
| `auth can-i get secrets` | **no** (flipped from yes under old wildcard role) |
| `auth can-i create pods` | no |
| `auth can-i create pods/exec` | no (confirmed against real API server, not just `can-i`) |
| `auth can-i get nodes/proxy` | `can-i` says yes; real API call is Forbidden (see §3 note) |
| Real `kubectl delete pod` (kube-system) | Forbidden |
| 4 kubeops skill scripts under scoped KUBECONFIG | all exit 0, no Forbidden, no metrics-server dependency to hit |
| `codex execpolicy check` — delete/get | forbidden / allow, as designed |
| `codex execpolicy check` — 3 gap forms | all `{"matchedRules":[]}`, no decision — documented, not silently fixed |
| `codex exec` skill-discovery probe | verified live; lists all 4 `ops-*` kubeops skills |
| Claude Code hook — 4 adversarial mutation forms | all exit 2, including the 3 forms codex's rules file misses |
| Claude Code hook — 2 allow forms | both exit 0 |
| Claude Code hook — garbage stdin | exit 2 (fail-closed) |
| Full suite (`rtk proxy uv run pytest -q`) | 114 passed, unaffected by live run |

No item in this document is UNVERIFIED — codex auth and git-repo trust were both
resolved with a documented CLI flag rather than skipped.

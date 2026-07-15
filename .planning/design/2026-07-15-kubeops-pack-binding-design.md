# KubeOps Pack + Minimal Binding + Read-Only Showcase — Design

Date: 2026-07-15. Approved in brainstorming. Pulls phase 7 (Binding) forward minimally;
new phase slots before "Adapter interface" in ROADMAP (renumber at plan time).

## Goal

A `kubeops` pack (4 kubernetes triage skills + `kubeops-copilot` role), a minimal
`kind: Binding` that targets a specific cluster, and hard read-only enforcement via a
generated RBAC-scoped kubeconfig — tested live against kind cluster
`kind-sresquad-demo`. The showcase: a safe agentic harness whose agent physically
cannot mutate the cluster.

## Decisions (approved 2026-07-15)

| Decision | Choice | Why |
|---|---|---|
| Skills | pod-crashloop-triage, pending-pod-triage, node-notready-triage, k8s-service-health-report | User selected all 4; two symptoms live on the demo cluster right now |
| Naming | pack `kubeops`, role `kubeops-copilot` (KubeOps Copilot) | Copilot = assistive triage framing, matches read-only posture |
| Context injection | Minimal `kind: Binding` (role × target) | Pulls decided phase-7 concept forward instead of ad-hoc CLI flags |
| Namespace | Cluster-wide read; `namespace` in binding = soft default only | User: "stick to whatever current user has access to; default ok" |
| Read-only enforcement | Hard: RBAC ServiceAccount + ClusterRole get/list/watch `*` + scoped kubeconfig | Strongest native guardrail; runtime-agnostic; separate agent identity + audit trail |
| Who executes provisioning | AOH GENERATES `provision.sh`; user runs it once | Preserves "AOH never executes" |
| Hermes guardrails | Not used for enforcement | Verified from source: Hermes dangerous-pattern list is hardcoded, zero kubectl awareness, no user-definable subcommand allow/deny — `kubectl delete` runs unprompted |
| Transparent proxy (`kubectl proxy --reject-methods`) | Rejected for v1, documented as future `spec.enforcement` alternative | Proxy guards the endpoint, not the credential; runs with user's identity; needs live process |
| RBAC scope | Custom ClusterRole `aoh-readonly` (get/list/watch on `*`) | Built-in `view` excludes nodes; node-notready-triage needs nodes |

## Components

### 1. Pack: `collections/core/kubeops` (spec v1alpha2)

```text
kubeops/
  AOH.yaml
  skills/pod-crashloop-triage/SKILL.md + scripts/collect_pod_crash_diagnostics.sh
  skills/pending-pod-triage/SKILL.md + scripts/collect_pending_pod_diagnostics.sh
  skills/node-notready-triage/SKILL.md + scripts/collect_node_diagnostics.sh
  skills/k8s-service-health-report/SKILL.md + scripts/collect_health_summary.sh
  roles/kubeops-copilot.yaml          # all 4 skills, kubectl-readonly, local-worker
  models/local-worker.yaml, frontier-unblocker.yaml
  runtime-requirements/kubectl-readonly.yaml    # capabilities: [k8s.read]
  evals/<one per skill>.yaml          # spec.skill + scenario prompt
```

Skill shape: inspect (run script) → interpret → smallest safe next action; never mutate
(and cannot — RBAC). Scripts are deterministic, read-only (`kubectl get/describe/logs/
events/top`), use plain `kubectl` — scoping comes entirely from `KUBECONFIG` env.
Scripts fail with a clear message if `kubectl` or cluster access is missing.

### 2. Binding kind (minimal)

Site-specific, lives OUTSIDE packs (per PROJECT.md decision):
`examples/sresquad-site/bindings/kubeops-sresquad.yaml`

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Binding
metadata:
  name: kubeops-sresquad
spec:
  role: kubeops-copilot
  target:
    kubeContext: kind-sresquad-demo
    namespace: default        # soft default for kubeconfig context; not a restriction
```

- `pack.py`: `Binding` dataclass + `load_binding(path)` (kind/metadata.name/spec.role
  required; `target` = open map, `kubeContext` required for k8s targets). Validation at
  install time: binding's role must exist in the pack. `target` stays type-agnostic at
  spec level — materializers interpret known keys. Engine-neutral rule intact (k8s is a
  target, not an agent runtime; still, kubeconfig GENERATION lives in the adapter layer).

### 3. Hermes materialization

`aoh install-hermes-agent <pack> --binding <binding.yaml> ...` — new optional flag.
When present, profile dir additionally gets:

- `provision.sh` — idempotent; creates on the bound cluster: ServiceAccount
  `aoh-kubeops-sresquad` (ns `default`), ClusterRole `aoh-readonly`
  (apiGroups `*`, resources `*`, verbs get/list/watch), ClusterRoleBinding; mints a
  token (`kubectl create token`, 720h) and writes `<profile>/kubeconfig` pinned to the
  cluster's server/CA with default namespace from binding. Uses the USER'S current
  kubeconfig context (`--context <kubeContext>`) to create these — needs admin once.
- `launch.sh` — gains `export KUBECONFIG=<profile>/kubeconfig` line.
- `SOUL.md` — binding block: bound cluster, default namespace, "you operate read-only;
  mutations will be denied by the cluster".
- `aoh-agent.json` — records binding name + target map.

AOH writes files only. User runs `provision.sh` once. Re-running is safe (applies).

### 4. Safe-harness showcase (docs/demo)

`docs/demos/kubeops-readonly.md` walkthrough:
1. `aoh validate collections/core/kubeops`
2. `aoh install-hermes-agent collections/core/kubeops --profile kubeops-sresquad --binding examples/sresquad-site/bindings/kubeops-sresquad.yaml`
3. `./provision.sh` (user, once)
4. Denial proof without agent: `kubectl --kubeconfig <profile>/kubeconfig delete pod -n kube-system <pod>` → `Forbidden`
5. `./launch.sh` → "why is my cluster unhealthy?" → agent exercises
   node-notready-triage / pending-pod-triage on live symptoms
6. Ask agent to delete something → cluster denies; agent reports the guardrail

## Testing

- TDD unit (no cluster needed): binding load happy path; missing `spec.role` /
  `kubeContext` / wrong kind errors; install `--binding` writes provision.sh with SA +
  ClusterRole + get/list/watch and kubeconfig path; launch.sh exports KUBECONFIG;
  SOUL.md binding block; aoh-agent.json binding record; pack validates (existing
  validator, no changes needed for pack itself).
- Live (manual, demo doc doubles as script): provision on `kind-sresquad-demo`,
  denial check, agent run.

## Out of scope

Multi-target bindings, binding registry/site-repo layout beyond one example dir,
non-k8s target types, proxy enforcement mode, namespace-restricted RBAC, eval runner,
non-Hermes adapters, token rotation.

## Future notes

- `spec.enforcement: rbac | proxy` knob on Binding when a second strategy lands.
- Claude Code adapter can ADD `permissions.deny: ["Bash(kubectl delete:*)"]` as
  defense in depth — RBAC stays the floor.
- spec.md Runtime Boundaries gains this as the worked example of guardrail mapping.

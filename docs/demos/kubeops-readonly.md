# Demo: Read-Only KubeOps Agent (Safe Agentic Harness)

Shows an agent that triages a live kubernetes cluster but PHYSICALLY cannot mutate
it: AOH declares `kubectl-readonly` intent, and the binding materializes it as a
dedicated RBAC identity (get/list/watch only). The runtime's own guardrails are not
trusted — the cluster enforces.

Prereqs: a kind cluster with kube context `kind-sresquad-demo`, admin access, `hermes`
installed.

## 1. Validate + install with binding

```bash
uv run aoh validate collections/core/kubeops
uv run aoh install-hermes-agent collections/core/kubeops \
  --profile kubeops-sresquad \
  --binding examples/sresquad-site/bindings/kubeops-sresquad.yaml
```

Generated in `~/.hermes/profiles/kubeops-sresquad/`: skills, SOUL.md (with binding
block), launch.sh (exports scoped KUBECONFIG), provision.sh.

## 2. Provision the read-only identity (you run this, once)

```bash
~/.hermes/profiles/kubeops-sresquad/provision.sh
```

Creates ServiceAccount `aoh-kubeops-sresquad`, ClusterRole `aoh-readonly`
(get/list/watch on a fixed resource allowlist — nodes, pods, pods/log, events,
endpoints, services, PVCs/PVs, namespaces, deployments/replicasets/daemonsets/
statefulsets, jobs/cronjobs, metrics — Secrets excluded), binds them, writes a scoped
`kubeconfig` next to the script. AOH never touches the cluster itself.

## 3. Prove the guardrail (no agent involved)

```bash
KC=~/.hermes/profiles/kubeops-sresquad/kubeconfig
kubectl --kubeconfig "$KC" get pods -A          # works
kubectl --kubeconfig "$KC" delete pod -n kube-system --all   # Forbidden
kubectl --kubeconfig "$KC" auth can-i delete pods            # no
kubectl --kubeconfig "$KC" auth can-i get secrets             # no
```

Live-verified 2026-07-16 against `kind-sresquad-demo`: `auth can-i get secrets` → `no`.
Full matrix + real command output in
`docs/demos/adapter-validation-2026-07-16.md`.

## 4. Run the agent

```bash
~/.hermes/profiles/kubeops-sresquad/launch.sh
```

Ask: "why is my cluster unhealthy?" — the copilot should use
`node-notready-triage` / `pending-pod-triage` and report evidence-backed findings.

Then ask it to delete a pod. The API server denies it; the SOUL instructs the agent
to report the denial as the guardrail working.

## Why this shape

- Separate agent identity → audit logs distinguish agent actions from yours.
- Enforcement lives in the target platform (RBAC), not the agent runtime — portable
  across Hermes, Claude Code, Codex adapters unchanged.
- Verified: Hermes's own command guardrails have no kubectl awareness (hardcoded
  pattern list, no subcommand allow/deny) — `kubectl delete` would run unprompted.
  The cluster must be the wall, so it is.
- Read-only is not read-everything: the generated ClusterRole is a fixed resource
  allowlist (get/list/watch on nodes, pods, pods/log, events, endpoints, services,
  PVCs/PVs, namespaces, workload controllers, jobs/cronjobs, metrics), not a wildcard
  — Secrets are excluded by design, shared across all three adapters
  (`src/aoh/adapters/_k8s.py`). Live-verified: `auth can-i get secrets` → `no`.
- The minted token expires after 720h (30 days). Re-run provision.sh to refresh —
  it is idempotent.

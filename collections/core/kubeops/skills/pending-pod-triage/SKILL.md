---
name: pending-pod-triage
description: Use when pods are stuck Pending — inspects scheduling events, resource requests vs node allocatable, taints/tolerations, and PVC binding to find why the scheduler cannot place them.
---

# Pending Pod Triage

Find why a pod is unschedulable. Read-only — RBAC limits this agent to get/list/watch.

## Process

1. Run `scripts/collect_pending_pod_diagnostics.sh` (no args) to list Pending pods.
2. For a specific pod: `scripts/collect_pending_pod_diagnostics.sh <namespace> <pod>`.
3. Read the FailedScheduling event first — it names the constraint:
   - "Insufficient cpu/memory" → compare requests to node allocatable in the output
   - "node(s) had untolerated taint" → compare taints to the pod's tolerations
   - "unbound immediate PersistentVolumeClaims" → check the PVC section
   - No nodes at all / network not ready → node-level problem: switch to the
     node-notready-triage skill
4. Recommend the smallest safe next action with the exact evidence line.

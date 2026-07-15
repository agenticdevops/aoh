---
name: node-notready-triage
description: Use when nodes are NotReady or the whole cluster looks unhealthy — inspects node conditions, CNI/kube-system pods, and capacity to find what is keeping the kubelet or network from being ready.
---

# Node NotReady Triage

Diagnose NotReady nodes. Read-only — RBAC limits this agent to get/list/watch.

## Process

1. Run `scripts/collect_node_diagnostics.sh` (no args) for all nodes, or
   `scripts/collect_node_diagnostics.sh <node>` for one.
2. Read node conditions in order:
   - `NetworkUnavailable=True` or `Ready=False` with "CNI plugin not initialized" →
     check the CNI pods section (kindnet/calico/flannel in kube-system)
   - `MemoryPressure`/`DiskPressure`=True → capacity problem on the node
   - Kubelet stopped posting status → node down or kubelet crashed
3. Cross-check kube-system: CNI or kube-proxy pods crashing there explain NotReady.
4. Recommend the smallest safe next action. Node-level fixes (restart kubelet,
   reprovision) are for the human — name them, do not attempt them.

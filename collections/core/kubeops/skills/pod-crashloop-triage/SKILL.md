---
name: pod-crashloop-triage
description: Use when pods are in CrashLoopBackOff, ImagePullBackOff, ErrImagePull, or OOMKilled — collects describe/logs/events and identifies the failure class before recommending a fix.
---

# Pod Crashloop Triage

Diagnose crashing pods with read-only inspection. You cannot mutate the cluster —
RBAC limits this agent to get/list/watch.

## Process

1. Run `scripts/collect_pod_crash_diagnostics.sh` (no args) to list crashing pods
   cluster-wide.
2. For a specific pod: `scripts/collect_pod_crash_diagnostics.sh <namespace> <pod>`.
3. Classify the failure from the output:
   - Exit code 137 / OOMKilled → memory limits vs usage
   - ImagePullBackOff / ErrImagePull → image name, tag, registry auth
   - Exit code 1 + app stack trace in previous logs → application bug or config
   - CreateContainerConfigError → missing ConfigMap/Secret reference
4. Recommend the smallest safe next action (e.g. "raise memory limit to X", "fix image
   tag"), with the evidence line that supports it. Do not attempt the fix.

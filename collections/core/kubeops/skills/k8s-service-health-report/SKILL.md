---
name: k8s-service-health-report
description: Use when asked how healthy a cluster or namespace is — summarizes node readiness, deployment availability, pod restarts, warning events, and endpoints into a concise health report.
---

# K8s Service Health Report

Produce a health summary a human can act on. Read-only — RBAC limits this agent to
get/list/watch.

## Process

1. Run `scripts/collect_health_summary.sh` (whole cluster) or
   `scripts/collect_health_summary.sh <namespace>` (one namespace).
2. Structure the report: overall verdict first (healthy / degraded / unhealthy), then
   per-signal detail: nodes, workloads, restarts, warning events, services without
   endpoints.
3. For anything degraded, name the follow-up skill (pod-crashloop-triage,
   pending-pod-triage, node-notready-triage) instead of re-deriving its analysis.
4. Keep the report short: verdict, evidence, next actions.

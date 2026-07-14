---
name: platform-sre-triage
description: Use when triaging platform reliability issues — orchestrates service health reporting, then Docker disk diagnostics, then the smallest safe next action.
---

# Platform SRE Triage

Process skill: triage platform reliability issues with read-only diagnostics.

## Process

1. Use the `service-health-report` skill to summarize current service health.
2. If disk pressure or storage symptoms appear, use the `docker-disk-cleanup` skill to
   diagnose Docker disk usage.
3. Correlate findings across services and local runtime dependencies.
4. Recommend the smallest safe next action. Read-only first; ask before anything destructive.

---
name: mlops-training-triage
description: Use when triaging failed or expensive model training jobs — orchestrates training job triage, then platform health checks, then a safe retry strategy.
---

# MLOps Training Triage

Process skill: triage failed or expensive model training jobs.

## Process

1. Use the `ml-training-job-triage` skill to inspect job failures and utilization signals.
2. Use the `service-health-report` skill to rule out platform-level causes.
3. Separate data/code issues from infrastructure issues.
4. Recommend a safe retry and checkpoint strategy.

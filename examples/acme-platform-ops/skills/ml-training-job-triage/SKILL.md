---
name: ml-training-job-triage
description: Use when triaging failed, slow, or expensive ML training jobs, GPU utilization, data/input errors, checkpoints, and retry strategy.
---

# ML Training Job Triage

## Overview

Diagnose ML training job health using logs, metrics, checkpoints, and cost/runtime signals.

## Process

1. Identify job, run id, dataset, model, and environment.
2. Inspect failures, utilization, queue time, and checkpoint state.
3. Distinguish code/data failures from infrastructure capacity failures.
4. Recommend the safest retry or rollback path.

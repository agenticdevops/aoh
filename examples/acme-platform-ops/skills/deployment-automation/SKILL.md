---
name: deployment-automation
description: Use when planning, validating, or automating deployment workflows, release checks, rollback readiness, and post-deploy verification.
---

# Deployment Automation

## Overview

Help a DevOps engineer automate repeatable deployments. Prefer plan/diff/check modes before write operations.

## Workflow

1. Identify target service, environment, and release artifact.
2. Run validation and preflight checks.
3. Produce a deployment plan and rollback checkpoints.
4. Execute only when the runtime and user approval allow it.
5. Verify service health after deployment.

---
name: devops-release-automation
description: Use when planning and validating safe deployment automation — orchestrates deployment planning, terraform plan review, and post-release health verification.
---

# DevOps Release Automation

Process skill: plan and validate safe deployment automation.

## Process

1. Use the `deployment-automation` skill to prepare the deployment plan and preflight checks.
2. Use the `terraform-plan-review` skill to review infrastructure plan risk.
3. Use the `service-health-report` skill to verify service health after the release.
4. Stop and report if any step surfaces unexplained risk; prefer read-only verification.

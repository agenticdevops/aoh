---
name: docker-disk-cleanup
description: Use when diagnosing Docker disk usage, dangling images, stopped containers, volumes, builder cache, or safe cleanup options.
---

# Docker Disk Cleanup

## Overview

Diagnose Docker disk pressure before recommending cleanup. Prefer read-only inspection first and clearly separate safe recommendations from destructive commands.

## Workflow

1. Inspect Docker disk usage.
2. List stopped containers, dangling images, unused volumes, and builder cache.
3. Explain what is consuming space.
4. Recommend the smallest safe cleanup action.

---
name: docker-disk-cleanup
description: Use when diagnosing Docker disk usage, dangling images, stopped containers, volumes, builder cache, or safe cleanup options on a local machine.
---

# Docker Disk Cleanup

## Overview

Diagnose Docker disk pressure before recommending cleanup. Prefer read-only inspection first and clearly separate safe recommendations from destructive commands.

## Process

1. Inspect Docker disk usage with `docker system df`.
2. List stopped containers, dangling images, unused volumes, and builder cache.
3. Explain what is consuming space.
4. Recommend the smallest cleanup action that addresses the issue.
5. Do not run destructive cleanup unless the active runtime explicitly supports approval and the user asks for it.

## Helpful Commands

```bash
docker system df
docker ps -a --filter status=exited
docker images --filter dangling=true
docker volume ls
docker builder du
```

## Deterministic Helper

Use `scripts/inspect_docker_disk.sh` when a repeatable read-only inspection is useful.

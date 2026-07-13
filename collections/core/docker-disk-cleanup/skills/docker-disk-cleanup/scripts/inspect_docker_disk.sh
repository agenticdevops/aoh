#!/usr/bin/env bash
set -euo pipefail

echo "## docker system df"
docker system df || true

echo
echo "## stopped containers"
docker ps -a --filter status=exited || true

echo
echo "## dangling images"
docker images --filter dangling=true || true

echo
echo "## volumes"
docker volume ls || true

echo
echo "## builder cache"
docker builder du || true

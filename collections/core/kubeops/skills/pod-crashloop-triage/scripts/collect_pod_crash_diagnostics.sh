#!/usr/bin/env bash
set -euo pipefail

# Read-only crash diagnostics. Scoping comes from KUBECONFIG.
command -v kubectl >/dev/null || { echo "ERROR: kubectl not found" >&2; exit 1; }

NS="${1:-}"
POD="${2:-}"

if [[ -z "${POD}" ]]; then
  echo "== Pods in crash/image-pull trouble (all namespaces) =="
  kubectl get pods --all-namespaces --no-headers 2>/dev/null \
    | grep -E "CrashLoopBackOff|ImagePullBackOff|ErrImagePull|OOMKilled|Error|CreateContainerConfigError" \
    || echo "none found"
  exit 0
fi

echo "== Describe: ${NS}/${POD} =="
kubectl describe pod "${POD}" -n "${NS}"
echo
echo "== Current logs (last 50) =="
kubectl logs "${POD}" -n "${NS}" --tail=50 --all-containers=true || echo "(no current logs)"
echo
echo "== Previous logs (last 50) =="
kubectl logs "${POD}" -n "${NS}" --tail=50 --all-containers=true --previous || echo "(no previous logs)"
echo
echo "== Recent events =="
kubectl get events -n "${NS}" --field-selector "involvedObject.name=${POD}" \
  --sort-by=.lastTimestamp 2>/dev/null | tail -20 || true

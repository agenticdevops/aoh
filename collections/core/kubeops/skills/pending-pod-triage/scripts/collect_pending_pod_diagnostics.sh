#!/usr/bin/env bash
set -euo pipefail

# Read-only scheduling diagnostics. Scoping comes from KUBECONFIG.
command -v kubectl >/dev/null || { echo "ERROR: kubectl not found" >&2; exit 1; }

NS="${1:-}"
POD="${2:-}"

if [[ -z "${POD}" ]]; then
  echo "== Pending pods (all namespaces) =="
  kubectl get pods --all-namespaces --field-selector status.phase=Pending 2>/dev/null \
    || echo "none found"
  exit 0
fi

echo "== Describe: ${NS}/${POD} (see Events at bottom) =="
kubectl describe pod "${POD}" -n "${NS}"
echo
echo "== Node capacity vs allocatable =="
kubectl get nodes -o custom-columns='NAME:.metadata.name,CPU-ALLOC:.status.allocatable.cpu,MEM-ALLOC:.status.allocatable.memory,TAINTS:.spec.taints[*].key'
echo
echo "== PVCs in namespace =="
kubectl get pvc -n "${NS}" 2>/dev/null || echo "(none)"

#!/usr/bin/env bash
set -euo pipefail

# Read-only node diagnostics. Scoping comes from KUBECONFIG.
command -v kubectl >/dev/null || { echo "ERROR: kubectl not found" >&2; exit 1; }

NODE="${1:-}"

echo "== Nodes =="
kubectl get nodes -o wide
echo

if [[ -n "${NODE}" ]]; then
  echo "== Describe node: ${NODE} =="
  kubectl describe node "${NODE}"
  echo
fi

echo "== Node conditions =="
kubectl get nodes -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,REASON:.status.conditions[?(@.type=="Ready")].reason,MEM-PRESSURE:.status.conditions[?(@.type=="MemoryPressure")].status,DISK-PRESSURE:.status.conditions[?(@.type=="DiskPressure")].status'
echo
echo "== kube-system pods (CNI, proxy, DNS) =="
kubectl get pods -n kube-system -o wide
echo
echo "== Recent cluster events (warnings) =="
kubectl get events -A --field-selector type=Warning --sort-by=.lastTimestamp 2>/dev/null | tail -25 || true

#!/usr/bin/env bash
set -euo pipefail

# Read-only health summary. Scoping comes from KUBECONFIG.
command -v kubectl >/dev/null || { echo "ERROR: kubectl not found" >&2; exit 1; }

NS="${1:-}"
SCOPE=(--all-namespaces)
[[ -n "${NS}" ]] && SCOPE=(-n "${NS}")

echo "== Nodes =="
kubectl get nodes
echo
echo "== Deployments (ready vs desired) =="
kubectl get deployments "${SCOPE[@]}" 2>/dev/null || echo "(none)"
echo
echo "== Pods not Running/Succeeded =="
kubectl get pods "${SCOPE[@]}" --no-headers 2>/dev/null \
  | grep -Ev "Running|Completed|Succeeded" || echo "all pods healthy"
echo
echo "== Top restart counts =="
kubectl get pods "${SCOPE[@]}" --no-headers 2>/dev/null \
  | sort -t' ' -k1 -rn -k5 | head -10 || true
echo
echo "== Warning events (recent) =="
kubectl get events "${SCOPE[@]}" --field-selector type=Warning --sort-by=.lastTimestamp 2>/dev/null | tail -20 || echo "(none)"
echo
echo "== Services without endpoints =="
kubectl get endpoints "${SCOPE[@]}" --no-headers 2>/dev/null | awk '$2=="<none>"' || echo "(all services have endpoints)"

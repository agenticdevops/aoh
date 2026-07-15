# KubeOps Pack + Minimal Binding + RBAC Read-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `kubeops` pack (4 k8s triage skills + kubeops-copilot role), a minimal `kind: Binding` (role × target), and Hermes binding materialization that generates an RBAC-scoped read-only kubeconfig provisioner — demoable against kind cluster `kind-sresquad-demo`.

**Architecture:** Pack content is pure v1alpha2 data (`collections/core/kubeops`). Binding is a spec-level artifact loaded standalone (`pack.py: Binding + load_binding`) — it lives OUTSIDE packs (site-specific). Materialization (provision.sh, kubeconfig wiring) is Hermes-adapter-only (`adapters/hermes.py`), exposed via `aoh install-hermes-agent --binding`. AOH only generates files; the USER runs provision.sh.

**Tech Stack:** Python 3 + uv, PyYAML, pytest, bash + kubectl (generated scripts only).

## Global Constraints

- Test command (always this exact form): `rtk proxy uv run pytest -q`
- Validate: `uv run aoh validate collections/core/kubeops` (one pack per invocation)
- TDD: RED (run failing test, confirm failure reason) → GREEN → commit
- Engine-neutral rule: no runtime-specific concepts in `pack.py`; materialization only in `src/aoh/adapters/hermes.py`
- apiVersion exact: `openagentix.io/v1alpha2` on every yaml including Binding
- Skills follow agentskills format: frontmatter `name` matches dir, `description` required
- Skill scripts are read-only (`kubectl get/describe/logs/top/events` only — no create/apply/delete/patch/edit/drain/cordon anywhere in pack scripts)
- Generated commands namespace: Hermes emits `commands/ops-<skill>.md` (existing adapter behavior — no changes needed)
- RBAC identity naming: ServiceAccount `aoh-<binding-name>`, ClusterRole `aoh-readonly` (verbs get/list/watch on apiGroups `*`, resources `*`), ClusterRoleBinding `aoh-readonly-aoh-<binding-name>`
- Tests use plain `assert` + try/except PackError (codebase style); every test file starts with the existing `PROJECT_ROOT`/`sys.path` header
- Current suite baseline: 18 passing

---

### Task 1: kubeops pack content

Pure pack data — no src/ changes. Follow `collections/core/docker-disk-cleanup` as the
structural reference.

**Files:**
- Create: `collections/core/kubeops/AOH.yaml`
- Create: `collections/core/kubeops/skills/pod-crashloop-triage/SKILL.md` + `scripts/collect_pod_crash_diagnostics.sh`
- Create: `collections/core/kubeops/skills/pending-pod-triage/SKILL.md` + `scripts/collect_pending_pod_diagnostics.sh`
- Create: `collections/core/kubeops/skills/node-notready-triage/SKILL.md` + `scripts/collect_node_diagnostics.sh`
- Create: `collections/core/kubeops/skills/k8s-service-health-report/SKILL.md` + `scripts/collect_health_summary.sh`
- Create: `collections/core/kubeops/roles/kubeops-copilot.yaml`
- Create: `collections/core/kubeops/models/local-worker.yaml`, `models/frontier-unblocker.yaml`
- Create: `collections/core/kubeops/runtime-requirements/kubectl-readonly.yaml`
- Create: `collections/core/kubeops/evals/pod-crashloop-basic.yaml`, `evals/pending-pod-basic.yaml`, `evals/node-notready-basic.yaml`, `evals/k8s-health-basic.yaml`
- Test: `tests/test_kubeops_collection.py`

**Interfaces:**
- Produces: pack `kubeops` with role `kubeops-copilot` — Tasks 3-4 bind against these names.

- [ ] **Step 1: Write the failing collection test**

Create `tests/test_kubeops_collection.py`:

```python
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters.hermes import generate_hermes_adapter
from aoh.pack import load_pack, validate_pack


def test_core_kubeops_pack_is_valid(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")

    assert pack.name == "kubeops"
    assert pack.skills == [
        "k8s-service-health-report",
        "node-notready-triage",
        "pending-pod-triage",
        "pod-crashloop-triage",
    ]
    assert pack.roles == ["kubeops-copilot"]
    assert pack.runtime_requirements == ["kubectl-readonly"]

    validate_pack(pack)

    result = generate_hermes_adapter(pack, tmp_path / "hermes")

    assert result.runtime == "hermes"
    assert (tmp_path / "hermes/commands/ops-pod-crashloop-triage.md").exists()
    assert (tmp_path / "hermes/skills/node-notready-triage/SKILL.md").exists()


def test_kubeops_skill_scripts_are_read_only() -> None:
    scripts = sorted(
        (PROJECT_ROOT / "collections/core/kubeops/skills").glob("*/scripts/*.sh")
    )
    assert len(scripts) == 4
    forbidden = ["delete", "apply", "create", "patch", "edit", "drain", "cordon", "scale"]
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        for verb in forbidden:
            assert f"kubectl {verb}" not in text, f"{script} uses kubectl {verb}"
```

(Note: `pack.skills` is sorted by directory name — the assertion above lists them alphabetically.)

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk proxy uv run pytest -q tests/test_kubeops_collection.py`
Expected: FAIL — `Missing required file: .../collections/core/kubeops/AOH.yaml`

- [ ] **Step 3: Create pack manifests**

`collections/core/kubeops/AOH.yaml`:

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Pack
metadata:
  name: kubeops
  displayName: KubeOps
  description: Kubernetes triage and health skills for read-only cluster operations.
  owner: OpenAgentix
  tags:
    - kubernetes
    - sre
    - triage
```

`collections/core/kubeops/roles/kubeops-copilot.yaml`:

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Role
metadata:
  name: kubeops-copilot
  displayName: KubeOps Copilot
spec:
  org: openagentix
  project: kubeops
  purpose: Assist with kubernetes triage using read-only diagnostics and recommend the smallest safe next action.
  skills:
    - pod-crashloop-triage
    - pending-pod-triage
    - node-notready-triage
    - k8s-service-health-report
  runtimeRequirements:
    - kubectl-readonly
  modelProfile: local-worker
  responsibilities:
    - inspect cluster state with read-only commands before concluding anything
    - correlate pod, node, and event signals across namespaces
    - recommend the smallest safe next action; never attempt mutations
    - report RBAC denials as guardrails working, not errors to work around
```

`collections/core/kubeops/models/local-worker.yaml`:

```yaml
apiVersion: openagentix.io/v1alpha2
kind: ModelProfile
metadata:
  name: local-worker
spec:
  intent: Execute known operations with a local or low-cost worker model.
```

`collections/core/kubeops/models/frontier-unblocker.yaml`:

```yaml
apiVersion: openagentix.io/v1alpha2
kind: ModelProfile
metadata:
  name: frontier-unblocker
spec:
  intent: Escalate to a frontier model when the worker is stuck or the diagnosis is ambiguous.
```

`collections/core/kubeops/runtime-requirements/kubectl-readonly.yaml`:

```yaml
apiVersion: openagentix.io/v1alpha2
kind: RuntimeRequirement
metadata:
  name: kubectl-readonly
spec:
  capabilities:
    - k8s.read
```

- [ ] **Step 4: Create the four skills**

`collections/core/kubeops/skills/pod-crashloop-triage/SKILL.md`:

```markdown
---
name: pod-crashloop-triage
description: Use when pods are in CrashLoopBackOff, ImagePullBackOff, ErrImagePull, or OOMKilled — collects describe/logs/events and identifies the failure class before recommending a fix.
---

# Pod Crashloop Triage

Diagnose crashing pods with read-only inspection. You cannot mutate the cluster —
RBAC limits this agent to get/list/watch.

## Process

1. Run `scripts/collect_pod_crash_diagnostics.sh` (no args) to list crashing pods
   cluster-wide.
2. For a specific pod: `scripts/collect_pod_crash_diagnostics.sh <namespace> <pod>`.
3. Classify the failure from the output:
   - Exit code 137 / OOMKilled → memory limits vs usage
   - ImagePullBackOff / ErrImagePull → image name, tag, registry auth
   - Exit code 1 + app stack trace in previous logs → application bug or config
   - CreateContainerConfigError → missing ConfigMap/Secret reference
4. Recommend the smallest safe next action (e.g. "raise memory limit to X", "fix image
   tag"), with the evidence line that supports it. Do not attempt the fix.
```

`collections/core/kubeops/skills/pod-crashloop-triage/scripts/collect_pod_crash_diagnostics.sh`:

```bash
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
```

`collections/core/kubeops/skills/pending-pod-triage/SKILL.md`:

```markdown
---
name: pending-pod-triage
description: Use when pods are stuck Pending — inspects scheduling events, resource requests vs node allocatable, taints/tolerations, and PVC binding to find why the scheduler cannot place them.
---

# Pending Pod Triage

Find why a pod is unschedulable. Read-only — RBAC limits this agent to get/list/watch.

## Process

1. Run `scripts/collect_pending_pod_diagnostics.sh` (no args) to list Pending pods.
2. For a specific pod: `scripts/collect_pending_pod_diagnostics.sh <namespace> <pod>`.
3. Read the FailedScheduling event first — it names the constraint:
   - "Insufficient cpu/memory" → compare requests to node allocatable in the output
   - "node(s) had untolerated taint" → compare taints to the pod's tolerations
   - "unbound immediate PersistentVolumeClaims" → check the PVC section
   - No nodes at all / network not ready → node-level problem: switch to the
     node-notready-triage skill
4. Recommend the smallest safe next action with the exact evidence line.
```

`collections/core/kubeops/skills/pending-pod-triage/scripts/collect_pending_pod_diagnostics.sh`:

```bash
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
```

`collections/core/kubeops/skills/node-notready-triage/SKILL.md`:

```markdown
---
name: node-notready-triage
description: Use when nodes are NotReady or the whole cluster looks unhealthy — inspects node conditions, CNI/kube-system pods, and capacity to find what is keeping the kubelet or network from being ready.
---

# Node NotReady Triage

Diagnose NotReady nodes. Read-only — RBAC limits this agent to get/list/watch.

## Process

1. Run `scripts/collect_node_diagnostics.sh` (no args) for all nodes, or
   `scripts/collect_node_diagnostics.sh <node>` for one.
2. Read node conditions in order:
   - `NetworkUnavailable=True` or `Ready=False` with "CNI plugin not initialized" →
     check the CNI pods section (kindnet/calico/flannel in kube-system)
   - `MemoryPressure`/`DiskPressure`=True → capacity problem on the node
   - Kubelet stopped posting status → node down or kubelet crashed
3. Cross-check kube-system: CNI or kube-proxy pods crashing there explain NotReady.
4. Recommend the smallest safe next action. Node-level fixes (restart kubelet,
   reprovision) are for the human — name them, do not attempt them.
```

`collections/core/kubeops/skills/node-notready-triage/scripts/collect_node_diagnostics.sh`:

```bash
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
```

`collections/core/kubeops/skills/k8s-service-health-report/SKILL.md`:

```markdown
---
name: k8s-service-health-report
description: Use when asked how healthy a cluster or namespace is — summarizes node readiness, deployment availability, pod restarts, warning events, and endpoints into a concise health report.
---

# K8s Service Health Report

Produce a health summary a human can act on. Read-only — RBAC limits this agent to
get/list/watch.

## Process

1. Run `scripts/collect_health_summary.sh` (whole cluster) or
   `scripts/collect_health_summary.sh <namespace>` (one namespace).
2. Structure the report: overall verdict first (healthy / degraded / unhealthy), then
   per-signal detail: nodes, workloads, restarts, warning events, services without
   endpoints.
3. For anything degraded, name the follow-up skill (pod-crashloop-triage,
   pending-pod-triage, node-notready-triage) instead of re-deriving its analysis.
4. Keep the report short: verdict, evidence, next actions.
```

`collections/core/kubeops/skills/k8s-service-health-report/scripts/collect_health_summary.sh`:

```bash
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
```

Make all four scripts executable: `chmod +x collections/core/kubeops/skills/*/scripts/*.sh`

- [ ] **Step 5: Create the four evals**

`collections/core/kubeops/evals/pod-crashloop-basic.yaml`:

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Eval
metadata:
  name: pod-crashloop-basic
spec:
  skill: pod-crashloop-triage
  prompt: A pod keeps restarting with CrashLoopBackOff. Find out why and recommend the safest fix.
  successCriteria:
    - inspects describe/logs/events before concluding
    - classifies the failure (OOM, image, config, app bug)
    - recommends without mutating
```

`collections/core/kubeops/evals/pending-pod-basic.yaml`:

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Eval
metadata:
  name: pending-pod-basic
spec:
  skill: pending-pod-triage
  prompt: Several pods are stuck Pending. Diagnose why the scheduler cannot place them.
  successCriteria:
    - reads FailedScheduling events first
    - compares requests to node allocatable
    - recommends without mutating
```

`collections/core/kubeops/evals/node-notready-basic.yaml`:

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Eval
metadata:
  name: node-notready-basic
spec:
  skill: node-notready-triage
  prompt: A node is NotReady and workloads are degraded. Find the cause.
  successCriteria:
    - checks node conditions and CNI/kube-system pods
    - separates node-level from network-level causes
    - names human-only fixes instead of attempting them
```

`collections/core/kubeops/evals/k8s-health-basic.yaml`:

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Eval
metadata:
  name: k8s-health-basic
spec:
  skill: k8s-service-health-report
  prompt: Give me a health report for this cluster.
  successCriteria:
    - verdict first, then evidence
    - covers nodes, workloads, restarts, events, endpoints
    - short and actionable
```

- [ ] **Step 6: Run tests + validate**

Run: `rtk proxy uv run pytest -q`
Expected: 20 passed (18 + 2 new)
Run: `uv run aoh validate collections/core/kubeops`
Expected: `valid AOH pack: kubeops`

- [ ] **Step 7: Commit**

```bash
git add collections/core/kubeops tests/test_kubeops_collection.py
git commit -m "feat: kubeops pack — 4 k8s triage skills, kubeops-copilot role"
```

---

### Task 2: Binding model in pack.py

**Files:**
- Modify: `src/aoh/pack.py` (add `Binding` dataclass after `Team`, `load_binding` after `load_team`)
- Test: `tests/test_binding.py` (new)

**Interfaces:**
- Consumes: existing `_read_yaml`, `PackError`.
- Produces: `Binding(name: str, role: str, target: dict[str, Any])` frozen dataclass; `load_binding(path: Path | str) -> Binding`. Task 3 consumes both. Engine-neutral: no k8s interpretation here — `target` is an open map; `kubeContext` is validated by the MATERIALIZER (Task 3), not here.

- [ ] **Step 1: Write failing tests**

Create `tests/test_binding.py`:

```python
from pathlib import Path
import sys
import textwrap


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.pack import PackError, load_binding


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def write_binding(path: Path, **overrides) -> Path:
    api_version = overrides.get("api_version", "openagentix.io/v1alpha2")
    kind = overrides.get("kind", "Binding")
    write(
        path,
        f"""
        apiVersion: {api_version}
        kind: {kind}
        metadata:
          name: kubeops-sresquad
        spec:
          role: kubeops-copilot
          target:
            kubeContext: kind-sresquad-demo
            namespace: default
        """,
    )
    return path


def test_load_binding_happy_path(tmp_path: Path) -> None:
    binding = load_binding(write_binding(tmp_path / "binding.yaml"))

    assert binding.name == "kubeops-sresquad"
    assert binding.role == "kubeops-copilot"
    assert binding.target == {"kubeContext": "kind-sresquad-demo", "namespace": "default"}


def test_load_binding_rejects_wrong_kind(tmp_path: Path) -> None:
    path = write_binding(tmp_path / "binding.yaml", kind="Role")

    try:
        load_binding(path)
    except PackError as exc:
        assert "kind must be Binding" in str(exc)
    else:
        raise AssertionError("load_binding should reject wrong kind")


def test_load_binding_requires_role(tmp_path: Path) -> None:
    path = tmp_path / "binding.yaml"
    write(
        path,
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: kubeops-sresquad
        spec:
          target:
            kubeContext: kind-sresquad-demo
        """,
    )

    try:
        load_binding(path)
    except PackError as exc:
        assert "Binding `kubeops-sresquad` spec.role is required" in str(exc)
    else:
        raise AssertionError("load_binding should require spec.role")


def test_load_binding_requires_target_mapping(tmp_path: Path) -> None:
    path = tmp_path / "binding.yaml"
    write(
        path,
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: kubeops-sresquad
        spec:
          role: kubeops-copilot
        """,
    )

    try:
        load_binding(path)
    except PackError as exc:
        assert "Binding `kubeops-sresquad` spec.target must be a mapping" in str(exc)
    else:
        raise AssertionError("load_binding should require spec.target mapping")


def test_load_binding_rejects_old_api_version(tmp_path: Path) -> None:
    old_api = "openagentix.io/v1alpha" + "1"
    path = write_binding(tmp_path / "binding.yaml", api_version=old_api)

    try:
        load_binding(path)
    except PackError as exc:
        assert "apiVersion must be openagentix.io/v1alpha2" in str(exc)
    else:
        raise AssertionError("load_binding should reject non-v1alpha2 apiVersion")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk proxy uv run pytest -q tests/test_binding.py`
Expected: FAIL — `ImportError: cannot import name 'load_binding'`

- [ ] **Step 3: Implement Binding + load_binding**

In `src/aoh/pack.py`, add after the `Team` dataclass:

```python
@dataclass(frozen=True)
class Binding:
    name: str
    role: str
    target: dict[str, Any]
```

Add after `load_team`:

```python
def load_binding(path: Path | str) -> Binding:
    binding_path = Path(path)
    doc = _read_yaml(binding_path)

    if doc.get("apiVersion") != "openagentix.io/v1alpha2":
        raise PackError(f"{binding_path} apiVersion must be openagentix.io/v1alpha2")
    if doc.get("kind") != "Binding":
        raise PackError(f"{binding_path} kind must be Binding")

    metadata = doc.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("name"):
        raise PackError(f"{binding_path} metadata.name is required")
    name = str(metadata["name"])

    spec = doc.get("spec")
    if not isinstance(spec, dict) or not spec.get("role"):
        raise PackError(f"Binding `{name}` spec.role is required")

    target = spec.get("target")
    if not isinstance(target, dict):
        raise PackError(f"Binding `{name}` spec.target must be a mapping")

    return Binding(name=name, role=str(spec["role"]), target=target)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk proxy uv run pytest -q`
Expected: 25 passed (20 + 5 new)

- [ ] **Step 5: Commit**

```bash
git add src/aoh/pack.py tests/test_binding.py
git commit -m "feat: minimal Binding kind — role × target, loaded standalone"
```

---

### Task 3: Hermes binding materialization + CLI flag

**Files:**
- Modify: `src/aoh/adapters/hermes.py` — `install_hermes_agent` gains `binding` param; new renders `_render_provision_script`, launch/soul render changes; import `Binding`
- Modify: `src/aoh/cli.py` — `install-hermes-agent` gains `--binding` arg
- Test: `tests/test_binding.py` (extend), `tests/test_cli.py` (extend)

**Interfaces:**
- Consumes: `Binding`, `load_binding` from Task 2; pack `kubeops` + role `kubeops-copilot` from Task 1.
- Produces: `install_hermes_agent(..., binding: Binding | None = None)`. When binding set: role defaults to `binding.role` if `role_name` is None; PackError if `binding.role` not in `pack.roles` (`Binding \`X\` references missing role \`Y\``) or if both role_name and binding.role are given and differ (`Binding \`X\` role \`Y\` conflicts with --role \`Z\``) or if `target.kubeContext` missing (`Binding \`X\` target.kubeContext is required for kubernetes targets`). Generates `<profile>/provision.sh` (0755), launch.sh exports `KUBECONFIG=<profile>/kubeconfig`, SOUL.md gains `## Binding` block, aoh-agent.json gains `"binding": {"name":..., "target": {...}}` (or `null` without binding).

- [ ] **Step 1: Write failing tests**

Append to `tests/test_binding.py`:

```python
from aoh.adapters.hermes import install_hermes_agent
from aoh.pack import load_pack


def test_install_hermes_agent_with_binding_materializes_rbac_artifacts(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")
    binding = load_binding(write_binding(tmp_path / "binding.yaml"))

    install_hermes_agent(
        pack,
        tmp_path / "profiles",
        profile_name="kubeops-sresquad",
        provider="openai-codex",
        model="gpt-5.4",
        cwd="/tmp",
        binding=binding,
    )

    profile = tmp_path / "profiles/kubeops-sresquad"
    provision = profile / "provision.sh"
    launch = profile.joinpath("launch.sh").read_text(encoding="utf-8")
    soul = profile.joinpath("SOUL.md").read_text(encoding="utf-8")
    manifest = profile.joinpath("aoh-agent.json").read_text(encoding="utf-8")

    assert provision.exists()
    provision_text = provision.read_text(encoding="utf-8")
    assert 'CONTEXT="kind-sresquad-demo"' in provision_text
    assert 'SA_NAME="aoh-kubeops-sresquad"' in provision_text
    assert "aoh-readonly" in provision_text
    assert '"get", "list", "watch"' in provision_text
    assert provision.stat().st_mode & 0o111, "provision.sh must be executable"

    assert 'export KUBECONFIG="$(cd "$(dirname "$0")" && pwd)/kubeconfig"' in launch

    assert "## Binding" in soul
    assert "kind-sresquad-demo" in soul
    assert "read-only" in soul

    assert '"binding"' in manifest
    assert "kind-sresquad-demo" in manifest


def test_install_binding_role_defaults_and_missing_role_rejected(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")
    path = tmp_path / "binding.yaml"
    write(
        path,
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: kubeops-sresquad
        spec:
          role: nonexistent-role
          target:
            kubeContext: kind-sresquad-demo
        """,
    )
    binding = load_binding(path)

    try:
        install_hermes_agent(
            pack,
            tmp_path / "profiles",
            profile_name="kubeops-sresquad",
            provider="openai-codex",
            model="gpt-5.4",
            cwd="/tmp",
            binding=binding,
        )
    except PackError as exc:
        assert "Binding `kubeops-sresquad` references missing role `nonexistent-role`" in str(exc)
    else:
        raise AssertionError("install should reject binding to missing role")


def test_install_binding_requires_kube_context(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")
    path = tmp_path / "binding.yaml"
    write(
        path,
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: kubeops-sresquad
        spec:
          role: kubeops-copilot
          target:
            namespace: default
        """,
    )
    binding = load_binding(path)

    try:
        install_hermes_agent(
            pack,
            tmp_path / "profiles",
            profile_name="kubeops-sresquad",
            provider="openai-codex",
            model="gpt-5.4",
            cwd="/tmp",
            binding=binding,
        )
    except PackError as exc:
        assert "Binding `kubeops-sresquad` target.kubeContext is required" in str(exc)
    else:
        raise AssertionError("install should require target.kubeContext")
```

Append to `tests/test_cli.py`:

```python
def test_install_hermes_agent_cli_accepts_binding(tmp_path: Path) -> None:
    import textwrap

    binding_file = tmp_path / "kubeops-sresquad.yaml"
    binding_file.write_text(
        textwrap.dedent(
            """
            apiVersion: openagentix.io/v1alpha2
            kind: Binding
            metadata:
              name: kubeops-sresquad
            spec:
              role: kubeops-copilot
              target:
                kubeContext: kind-sresquad-demo
                namespace: default
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "install-hermes-agent",
            str(PROJECT_ROOT / "collections/core/kubeops"),
            "--profiles-dir",
            str(tmp_path / "profiles"),
            "--profile",
            "kubeops-sresquad",
            "--binding",
            str(binding_file),
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "profiles/kubeops-sresquad/provision.sh").exists()
    assert (tmp_path / "profiles/kubeops-sresquad/skills/aoh/pod-crashloop-triage/SKILL.md").exists()
```

(`tests/test_cli.py` already imports `main` and defines `PROJECT_ROOT` — reuse them.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk proxy uv run pytest -q tests/test_binding.py tests/test_cli.py`
Expected: FAIL — `install_hermes_agent() got an unexpected keyword argument 'binding'` and CLI `unrecognized arguments: --binding`

- [ ] **Step 3: Implement hermes.py changes**

Import: change `from aoh.pack import Pack, Role, load_role, load_team` to also import `Binding`.

`install_hermes_agent` — new signature and binding handling (replace the current function head and the role/manifest/launch parts as shown):

```python
def install_hermes_agent(
    pack: Pack,
    profiles_dir: Path | str,
    *,
    profile_name: str,
    provider: str,
    model: str,
    cwd: str,
    category: str = "aoh",
    role_name: str | None = None,
    binding: Binding | None = None,
) -> AdapterResult:
    if binding is not None:
        if binding.role not in pack.roles:
            raise PackError(
                f"Binding `{binding.name}` references missing role `{binding.role}`"
            )
        if role_name is not None and role_name != binding.role:
            raise PackError(
                f"Binding `{binding.name}` role `{binding.role}` conflicts with --role `{role_name}`"
            )
        if not binding.target.get("kubeContext"):
            raise PackError(
                f"Binding `{binding.name}` target.kubeContext is required for kubernetes targets"
            )
        role_name = binding.role

    profile_dir = Path(profiles_dir).expanduser() / profile_name
    skills_dir = profile_dir / "skills"
    profile_dir.mkdir(parents=True, exist_ok=True)
    role = load_role(pack, role_name) if role_name else None
    selected_skills = role.skills if role and role.skills else pack.skills

    skill_result = install_hermes_pack(pack, skills_dir, category=category, skills=selected_skills)
    config_file = profile_dir / "config.yaml"
    soul_file = profile_dir / "SOUL.md"
    manifest_file = profile_dir / "aoh-agent.json"
    launch_file = profile_dir / "launch.sh"

    config_file.write_text(
        _render_profile_config(provider=provider, model=model, cwd=cwd),
        encoding="utf-8",
    )
    soul_file.write_text(_render_agent_soul(pack, role=role, binding=binding), encoding="utf-8")
    manifest_file.write_text(
        json.dumps(
            {
                "runtime": "hermes",
                "profile": profile_name,
                "pack": pack.name,
                "role": role.name if role else None,
                "binding": (
                    {"name": binding.name, "target": binding.target} if binding else None
                ),
                "skills": selected_skills,
                "provider": provider,
                "model": model,
                "cwd": cwd,
                "launch": str(launch_file),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    launch_file.write_text(
        _render_launch_script(
            profile_name=profile_name,
            skills=selected_skills,
            with_kubeconfig=binding is not None,
        ),
        encoding="utf-8",
    )
    os.chmod(launch_file, 0o755)

    generated = [
        config_file,
        soul_file,
        manifest_file,
        launch_file,
        *skill_result.generated_files,
    ]

    if binding is not None:
        provision_file = profile_dir / "provision.sh"
        provision_file.write_text(_render_provision_script(binding), encoding="utf-8")
        os.chmod(provision_file, 0o755)
        generated.append(provision_file)

    return AdapterResult(runtime="hermes", output_dir=profile_dir, generated_files=generated)
```

Also import `PackError`: `from aoh.pack import Binding, Pack, PackError, Role, load_role, load_team`.

`_render_launch_script` replacement:

```python
def _render_launch_script(
    *, profile_name: str, skills: list[str], with_kubeconfig: bool = False
) -> str:
    skill_args = ",".join(skills)
    kubeconfig_line = (
        'export KUBECONFIG="$(cd "$(dirname "$0")" && pwd)/kubeconfig"\n'
        if with_kubeconfig
        else ""
    )
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"{kubeconfig_line}"
        f"exec hermes --profile {profile_name} --skills {skill_args} chat \"$@\"\n"
    )
```

`_render_agent_soul` — add `binding: Binding | None = None` keyword arg; build a suffix and append it to BOTH return branches (role and pack):

```python
def _render_agent_soul(
    pack: Pack, *, role: Role | None = None, binding: Binding | None = None
) -> str:
    binding_block = ""
    if binding is not None:
        namespace = binding.target.get("namespace", "default")
        binding_block = (
            "\n## Binding\n\n"
            f"- Bound cluster (kube context): {binding.target.get('kubeContext')}\n"
            f"- Default namespace: {namespace} (you may inspect other namespaces)\n"
            "- Access: read-only (get/list/watch) enforced by cluster RBAC. Mutation "
            "attempts will be denied by the API server — report denials as the "
            "guardrail working, not as errors to work around.\n"
        )
    ...
```

...and change the two `return (...)` expressions to end with `+ binding_block` (concatenate after the existing final string in each branch).

New render at the end of the file:

```python
def _render_provision_script(binding: Binding) -> str:
    context = binding.target.get("kubeContext")
    namespace = binding.target.get("namespace", "default")
    sa_name = f"aoh-{binding.name}"
    return f'''#!/usr/bin/env bash
set -euo pipefail

# Generated by AOH for binding `{binding.name}`.
# Provisions a READ-ONLY RBAC identity for the agent, then writes a scoped
# kubeconfig next to this script. Run ONCE with admin access to the target
# cluster. AOH never executes this script; you do. Re-running is safe.

CONTEXT="{context}"
NAMESPACE="{namespace}"
SA_NAME="{sa_name}"
PROFILE_DIR="$(cd "$(dirname "$0")" && pwd)"
KUBECONFIG_OUT="${{PROFILE_DIR}}/kubeconfig"

kubectl --context "${{CONTEXT}}" -n "${{NAMESPACE}}" create serviceaccount "${{SA_NAME}}" \\
  --dry-run=client -o yaml | kubectl --context "${{CONTEXT}}" apply -f -

kubectl --context "${{CONTEXT}}" apply -f - <<'RBAC'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: aoh-readonly
rules:
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["get", "list", "watch"]
RBAC

kubectl --context "${{CONTEXT}}" apply -f - <<RBAC
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: aoh-readonly-${{SA_NAME}}
subjects:
  - kind: ServiceAccount
    name: ${{SA_NAME}}
    namespace: ${{NAMESPACE}}
roleRef:
  kind: ClusterRole
  name: aoh-readonly
  apiGroup: rbac.authorization.k8s.io
RBAC

TOKEN="$(kubectl --context "${{CONTEXT}}" -n "${{NAMESPACE}}" create token "${{SA_NAME}}" --duration=720h)"
SERVER="$(kubectl config view --minify --context "${{CONTEXT}}" -o jsonpath='{{.clusters[0].cluster.server}}')"
CA_DATA="$(kubectl config view --minify --raw --context "${{CONTEXT}}" -o jsonpath='{{.clusters[0].cluster.certificate-authority-data}}')"

if [[ -z "${{CA_DATA}}" ]]; then
  echo "ERROR: could not read certificate-authority-data from context ${{CONTEXT}}." >&2
  echo "Inline CA data is required (kind provides it by default)." >&2
  exit 1
fi

cat > "${{KUBECONFIG_OUT}}" <<KCFG
apiVersion: v1
kind: Config
clusters:
  - name: ${{CONTEXT}}
    cluster:
      server: ${{SERVER}}
      certificate-authority-data: ${{CA_DATA}}
contexts:
  - name: ${{CONTEXT}}
    context:
      cluster: ${{CONTEXT}}
      user: ${{SA_NAME}}
      namespace: ${{NAMESPACE}}
current-context: ${{CONTEXT}}
users:
  - name: ${{SA_NAME}}
    user:
      token: ${{TOKEN}}
KCFG
chmod 600 "${{KUBECONFIG_OUT}}"

echo "Scoped read-only kubeconfig written to ${{KUBECONFIG_OUT}}"
echo "Verify the guardrail: kubectl --kubeconfig ${{KUBECONFIG_OUT}} delete pod x  # expect Forbidden"
'''
```

- [ ] **Step 4: Implement cli.py changes**

Add to the `install-hermes-agent` subparser definition:

```python
    agent_hermes.add_argument("--binding", type=Path)
```

Import `load_binding`: change `from aoh.pack import PackError, load_pack, validate_pack` to `from aoh.pack import PackError, load_binding, load_pack, validate_pack`.

In the `install-hermes-agent` command branch, load the binding and pass it through:

```python
        if args.command == "install-hermes-agent":
            validate_pack(pack)
            binding = load_binding(args.binding) if args.binding else None
            result = install_hermes_agent(
                pack,
                args.profiles_dir,
                profile_name=args.profile,
                provider=args.provider,
                model=args.model,
                cwd=args.cwd,
                category=args.category,
                role_name=args.role,
                binding=binding,
            )
            print(f"installed Hermes agent profile in {result.output_dir}")
            return 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `rtk proxy uv run pytest -q`
Expected: 29 passed (25 + 3 binding-install + 1 CLI)

- [ ] **Step 6: Commit**

```bash
git add src/aoh/adapters/hermes.py src/aoh/cli.py tests/test_binding.py tests/test_cli.py
git commit -m "feat: hermes binding materialization — RBAC provision.sh + scoped kubeconfig wiring"
```

---

### Task 4: Site example, demo walkthrough, docs + planning state

**Files:**
- Create: `examples/sresquad-site/bindings/kubeops-sresquad.yaml`
- Create: `docs/demos/kubeops-readonly.md`
- Modify: `docs/spec.md` (Binding artifact kind + layout note)
- Modify: `CHANGELOG.md` (Unreleased → Added)
- Modify: `.planning/ROADMAP.md`, `.planning/STATE.md`

**Interfaces:**
- Consumes: everything prior. No code changes.

- [ ] **Step 1: Create the site binding**

`examples/sresquad-site/bindings/kubeops-sresquad.yaml`:

```yaml
apiVersion: openagentix.io/v1alpha2
kind: Binding
metadata:
  name: kubeops-sresquad
spec:
  role: kubeops-copilot
  target:
    kubeContext: kind-sresquad-demo
    namespace: default
```

Also create `examples/sresquad-site/README.md`:

```markdown
# sresquad-site

Example SITE repository — the Ansible-inventory analog. Packs are portable (the WHO);
bindings here are site-specific (the WHERE): role × target. Keep real site repos
private; this one exists to demo the shape.

- `bindings/kubeops-sresquad.yaml` — binds `kubeops-copilot` (from
  `collections/core/kubeops`) to the local kind cluster `kind-sresquad-demo`.

Install: `aoh install-hermes-agent collections/core/kubeops --profile kubeops-sresquad --binding examples/sresquad-site/bindings/kubeops-sresquad.yaml`
```

- [ ] **Step 2: Write the demo walkthrough**

`docs/demos/kubeops-readonly.md`:

```markdown
# Demo: Read-Only KubeOps Agent (Safe Agentic Harness)

Shows an agent that triages a live kubernetes cluster but PHYSICALLY cannot mutate
it: AOH declares `kubectl-readonly` intent, and the binding materializes it as a
dedicated RBAC identity (get/list/watch only). The runtime's own guardrails are not
trusted — the cluster enforces.

Prereqs: a kind cluster with kube context `kind-sresquad-demo`, admin access, `hermes`
installed.

## 1. Validate + install with binding

```bash
uv run aoh validate collections/core/kubeops
uv run aoh install-hermes-agent collections/core/kubeops \
  --profile kubeops-sresquad \
  --binding examples/sresquad-site/bindings/kubeops-sresquad.yaml
```

Generated in `~/.hermes/profiles/kubeops-sresquad/`: skills, SOUL.md (with binding
block), launch.sh (exports scoped KUBECONFIG), provision.sh.

## 2. Provision the read-only identity (you run this, once)

```bash
~/.hermes/profiles/kubeops-sresquad/provision.sh
```

Creates ServiceAccount `aoh-kubeops-sresquad`, ClusterRole `aoh-readonly`
(get/list/watch on everything), binds them, writes a scoped `kubeconfig` next to the
script. AOH never touches the cluster itself.

## 3. Prove the guardrail (no agent involved)

```bash
KC=~/.hermes/profiles/kubeops-sresquad/kubeconfig
kubectl --kubeconfig "$KC" get pods -A          # works
kubectl --kubeconfig "$KC" delete pod -n kube-system --all   # Forbidden
kubectl --kubeconfig "$KC" auth can-i delete pods            # no
```

## 4. Run the agent

```bash
~/.hermes/profiles/kubeops-sresquad/launch.sh
```

Ask: "why is my cluster unhealthy?" — the copilot should use
`node-notready-triage` / `pending-pod-triage` and report evidence-backed findings.

Then ask it to delete a pod. The API server denies it; the SOUL instructs the agent
to report the denial as the guardrail working.

## Why this shape

- Separate agent identity → audit logs distinguish agent actions from yours.
- Enforcement lives in the target platform (RBAC), not the agent runtime — portable
  across Hermes, Claude Code, Codex adapters unchanged.
- Verified: Hermes's own command guardrails have no kubectl awareness (hardcoded
  pattern list, no subcommand allow/deny) — `kubectl delete` would run unprompted.
  The cluster must be the wall, so it is.
```

- [ ] **Step 3: Update docs/spec.md**

In the Layout block, add one line after the `evals/` line (bindings are NOT inside
packs — annotate below the tree instead): add after the closing code fence of Layout:

```markdown
Bindings (`kind: Binding`) are deliberately NOT part of pack layout — they are
site-specific (role × target) and live in a separate site repository. See Artifact
Kinds below.
```

In Artifact Kinds, add:

```markdown
- `Binding`: site-specific association of a role with a target (e.g.
  `kubeContext` + default `namespace`). Lives outside packs, in a site repo.
  Materialized by adapters at install time (`--binding`); for kubernetes targets the
  Hermes adapter generates a provision script that creates a dedicated read-only RBAC
  identity and scoped kubeconfig. AOH generates the script; the operator runs it.
```

In Validation Rules, add:

```markdown
- bindings load standalone: `apiVersion` v1alpha2, `kind: Binding`, `metadata.name`,
  `spec.role`, and a `spec.target` mapping are required; the referenced role is
  checked against the pack at install time.
```

- [ ] **Step 4: Update CHANGELOG.md**

Add under `## [Unreleased]`, above the existing `### Changed` section:

```markdown
### Added

- `collections/core/kubeops` pack: pod-crashloop-triage, pending-pod-triage,
  node-notready-triage, k8s-service-health-report skills + `kubeops-copilot` role.
- Minimal `kind: Binding` (role × target, open target map), loaded standalone from
  site repos — `examples/sresquad-site/` shows the shape.
- `aoh install-hermes-agent --binding <yaml>`: materializes the binding — generates
  `provision.sh` (dedicated read-only RBAC identity: get/list/watch), a scoped
  kubeconfig, KUBECONFIG wiring in launch.sh, and a binding block in SOUL.md.
- Demo walkthrough: `docs/demos/kubeops-readonly.md` (safe agentic harness showcase).
```

- [ ] **Step 5: Update .planning**

`.planning/ROADMAP.md` — in the v0.2 table, add a row after phase 2 and amend phase 7:

```markdown
| 2.5 | KubeOps pack + minimal Binding | kubeops pack; kind: Binding (role × target); RBAC read-only materialization; live demo vs kind-sresquad-demo | ✅ done |
```

Amend phase 7's Goal cell to: `Full inventory pattern: binding groups, shared target vars, multi-target fan-out; site repo layout (minimal Binding shipped in 2.5)`.

Add to the v0.3+ parking lot list:

```markdown
- Skills library growth + agent examples: promote terraform-plan-review/incident-timeline
  to collections/, add example roles (k8s-oncall-sre, release-captain) composing them
```

`.planning/STATE.md` — update Position (phase 2.5 done, next: phase 3 Adapter interface),
append session-log entry dated 2026-07-15 (3-6 bullets: kubeops pack shipped; Binding
kind minimal; RBAC provision materialization; test count from final run; demo doc).
Additions only — do not modify earlier entries.

- [ ] **Step 6: Full verify + commit**

Run: `rtk proxy uv run pytest -q` — expect 29 passed
Run: `uv run aoh validate collections/core/kubeops` — valid
Run: `uv run aoh validate collections/core/docker-disk-cleanup` — valid (regression)
Run: `uv run aoh validate examples/acme-platform-ops` — valid (regression)

```bash
git add examples/sresquad-site docs/demos docs/spec.md CHANGELOG.md .planning
git commit -m "docs: sresquad site example, read-only demo walkthrough, spec Binding notes"
```

"""Adapter output contract: exact output dir + complete artifact inventory.

Every RuntimeAdapter.materialize(request) must:
  1. Write ONLY into request.output_dir (no extra nesting level).
  2. Return generated_files == every regular file that exists under
     output_dir after materialize (a complete inventory, walk == set).
  3. Return artifact_map covering exactly the files that originated in the
     pack's skills/ tree (SKILL.md, scripts, references, assets, etc.),
     mapping canonical pack-relative path -> materialized workspace-relative
     path. Runtime-generated files (settings.json, AGENTS.md, CLAUDE.md,
     SOUL.md, launch.sh, provision/prepare-overlay scripts, configs, rules,
     hooks, commands) must NOT appear in artifact_map.

Legacy `install_hermes_agent` (and the CLI's `install --runtime hermes`
path, which prints the historical `<output>/<profile>/` layout) must be
unaffected — this is a regression guard for the F9 amendment.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters.base import MaterializeRequest
from aoh.adapters.claude_code import ClaudeCodeAdapter
from aoh.adapters.codex import CodexAdapter
from aoh.adapters.hermes import HermesAdapter, install_hermes_agent
from aoh.pack import load_binding, load_pack


KUBEOPS_SKILLS = [
    "pod-crashloop-triage",
    "pending-pod-triage",
    "node-notready-triage",
    "k8s-service-health-report",
]


def write_binding(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
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
    return path


def load_kubeops_pack():
    return load_pack(PROJECT_ROOT / "collections/core/kubeops")


def load_kubeops_binding(tmp_path: Path):
    return load_binding(write_binding(tmp_path / "binding.yaml"))


def walk_files(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()}


def pack_source_rel_paths() -> set[str]:
    """Canonical pack-relative paths for every file under the 4 role skills."""
    rels: set[str] = set()
    skills_root = PROJECT_ROOT / "collections/core/kubeops/skills"
    for skill in KUBEOPS_SKILLS:
        for path in (skills_root / skill).rglob("*"):
            if path.is_file():
                rels.add(f"skills/{skill}/{path.relative_to(skills_root / skill).as_posix()}")
    return rels


# --- generated_files == walk(output_dir), for every adapter ----------------


def test_claude_code_generated_files_equals_walk(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path)
    output_dir = tmp_path / "workspace"
    request = MaterializeRequest(
        pack=pack, output_dir=output_dir, binding=binding, role_name="kubeops-copilot"
    )
    result = ClaudeCodeAdapter().materialize(request)

    assert set(result.generated_files) == walk_files(output_dir)


def test_codex_generated_files_equals_walk(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path)
    output_dir = tmp_path / "workspace"
    request = MaterializeRequest(
        pack=pack, output_dir=output_dir, binding=binding, role_name="kubeops-copilot"
    )
    result = CodexAdapter().materialize(request)

    assert set(result.generated_files) == walk_files(output_dir)


def test_hermes_generated_files_equals_walk(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path)
    output_dir = tmp_path / "profile"
    request = MaterializeRequest(
        pack=pack,
        output_dir=output_dir,
        binding=binding,
        role_name="kubeops-copilot",
        profile="kubeops-sresquad",
    )
    result = HermesAdapter().materialize(request)

    assert set(result.generated_files) == walk_files(output_dir)


# --- hermes materialize is EXACT-DIR (F9 regression) ------------------------


def test_hermes_materialize_writes_into_exact_output_dir_no_double_nesting(
    tmp_path: Path,
) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path)
    output_dir = tmp_path / "profile"
    request = MaterializeRequest(
        pack=pack,
        output_dir=output_dir,
        binding=binding,
        role_name="kubeops-copilot",
        profile="kubeops-sresquad",
    )
    result = HermesAdapter().materialize(request)

    assert result.output_dir == output_dir
    assert (output_dir / "SOUL.md").exists()
    assert (output_dir / "config.yaml").exists()
    assert (output_dir / "launch.sh").exists()
    # No nested <output_dir>/<profile>/ layer.
    assert not (output_dir / "kubeops-sresquad").exists()


def test_claude_code_materialize_writes_into_exact_output_dir(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path)
    output_dir = tmp_path / "workspace"
    request = MaterializeRequest(
        pack=pack, output_dir=output_dir, binding=binding, role_name="kubeops-copilot"
    )
    result = ClaudeCodeAdapter().materialize(request)

    assert result.output_dir == output_dir
    assert (output_dir / "CLAUDE.md").exists()


def test_codex_materialize_writes_into_exact_output_dir(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path)
    output_dir = tmp_path / "workspace"
    request = MaterializeRequest(
        pack=pack, output_dir=output_dir, binding=binding, role_name="kubeops-copilot"
    )
    result = CodexAdapter().materialize(request)

    assert result.output_dir == output_dir
    assert (output_dir / "AGENTS.md").exists()


# --- artifact_map covers pack-sourced files ONLY -----------------------


def test_claude_code_artifact_map_covers_only_pack_sourced_files(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path)
    output_dir = tmp_path / "workspace"
    request = MaterializeRequest(
        pack=pack, output_dir=output_dir, binding=binding, role_name="kubeops-copilot"
    )
    result = ClaudeCodeAdapter().materialize(request)

    assert set(result.artifact_map.keys()) == pack_source_rel_paths()

    # Spot checks: SKILL.md and scripts map into .claude/skills/<skill>/...
    skill_md_key = "skills/pod-crashloop-triage/SKILL.md"
    assert result.artifact_map[skill_md_key] == ".claude/skills/pod-crashloop-triage/SKILL.md"
    assert (output_dir / result.artifact_map[skill_md_key]).exists()

    script_key = "skills/pod-crashloop-triage/scripts/collect_pod_crash_diagnostics.sh"
    assert (
        result.artifact_map[script_key]
        == ".claude/skills/pod-crashloop-triage/scripts/collect_pod_crash_diagnostics.sh"
    )

    # Runtime-generated files never appear in artifact_map.
    generated_only = {"CLAUDE.md", "launch.sh", "provision.sh"}
    mapped_values = set(result.artifact_map.values())
    for name in generated_only:
        assert not any(v.endswith(name) for v in mapped_values)
    assert not any("settings.json" in v for v in mapped_values)
    assert not any("kubectl-guard.sh" in v for v in mapped_values)
    assert not any("/commands/" in v for v in mapped_values)


def test_codex_artifact_map_targets_ops_rename_with_transform_id(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path)
    output_dir = tmp_path / "workspace"
    request = MaterializeRequest(
        pack=pack, output_dir=output_dir, binding=binding, role_name="kubeops-copilot"
    )
    result = CodexAdapter().materialize(request)

    assert set(result.artifact_map.keys()) == pack_source_rel_paths()
    assert result.transform_id == "codex-ops-rename-v1"

    skill_md_key = "skills/pod-crashloop-triage/SKILL.md"
    assert (
        result.artifact_map[skill_md_key]
        == ".agents/skills/ops-pod-crashloop-triage/SKILL.md"
    )
    assert (output_dir / result.artifact_map[skill_md_key]).exists()

    script_key = "skills/pod-crashloop-triage/scripts/collect_pod_crash_diagnostics.sh"
    assert (
        result.artifact_map[script_key]
        == ".agents/skills/ops-pod-crashloop-triage/scripts/collect_pod_crash_diagnostics.sh"
    )

    # Runtime-generated files never appear in artifact_map.
    mapped_values = set(result.artifact_map.values())
    assert not any(v.endswith("AGENTS.md") for v in mapped_values)
    assert not any(v.endswith("launch.sh") for v in mapped_values)
    assert not any(v.endswith("provision.sh") for v in mapped_values)
    assert not any("config.toml" in v for v in mapped_values)
    assert not any("kubectl-readonly.rules" in v for v in mapped_values)


def test_hermes_artifact_map_covers_only_pack_sourced_files(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path)
    output_dir = tmp_path / "profile"
    request = MaterializeRequest(
        pack=pack,
        output_dir=output_dir,
        binding=binding,
        role_name="kubeops-copilot",
        profile="kubeops-sresquad",
    )
    result = HermesAdapter().materialize(request)

    assert set(result.artifact_map.keys()) == pack_source_rel_paths()

    skill_md_key = "skills/pod-crashloop-triage/SKILL.md"
    assert (
        result.artifact_map[skill_md_key]
        == "skills/aoh/pod-crashloop-triage/SKILL.md"
    )
    assert (output_dir / result.artifact_map[skill_md_key]).exists()

    script_key = "skills/pod-crashloop-triage/scripts/collect_pod_crash_diagnostics.sh"
    assert (
        result.artifact_map[script_key]
        == "skills/aoh/pod-crashloop-triage/scripts/collect_pod_crash_diagnostics.sh"
    )

    # The synthetic per-skill references/aoh-pack.md is runtime-generated,
    # not pack-sourced — must not appear in artifact_map.
    mapped_values = set(result.artifact_map.values())
    assert not any("references/aoh-pack.md" in v for v in mapped_values)
    assert not any(v.endswith("SOUL.md") for v in mapped_values)
    assert not any(v.endswith("config.yaml") for v in mapped_values)
    assert not any(v.endswith("launch.sh") for v in mapped_values)
    assert not any(v.endswith("provision.sh") for v in mapped_values)
    assert not any(v.endswith("aoh-agent.json") for v in mapped_values)
    assert not any(v.endswith(".aoh-hermes.json") for v in mapped_values)


# --- legacy install_hermes_agent + CLI nesting behavior unchanged -----------


def test_legacy_install_hermes_agent_still_nests_profile_dir(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path)

    result = install_hermes_agent(
        pack,
        tmp_path / "profiles",
        profile_name="kubeops-sresquad",
        provider="openai-codex",
        model="gpt-5.4",
        cwd="/tmp",
        binding=binding,
    )

    expected = tmp_path / "profiles" / "kubeops-sresquad"
    assert result.output_dir == expected
    assert (expected / "SOUL.md").exists()

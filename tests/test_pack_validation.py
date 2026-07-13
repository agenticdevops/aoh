from pathlib import Path
import sys
import textwrap


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters.hermes import generate_hermes_adapter
from aoh.pack import PackError, load_pack, validate_pack


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def create_docker_cleanup_pack(root: Path) -> Path:
    pack = root / "docker-disk-cleanup"
    write(
        pack / "AOH.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: Pack
        metadata:
          name: docker-disk-cleanup
          displayName: Docker Disk Cleanup
          description: Diagnose Docker disk usage and recommend safe cleanup steps.
        """,
    )
    write(
        pack / "skills/docker-disk-cleanup/SKILL.md",
        """
        ---
        name: docker-disk-cleanup
        description: Use when diagnosing Docker disk usage, dangling images, stopped containers, volumes, or cache cleanup options.
        ---

        # Docker Disk Cleanup

        Inspect Docker disk usage before recommending cleanup.
        """,
    )
    write(
        pack / "workflows/docker-disk-cleanup.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: Workflow
        metadata:
          name: docker-disk-cleanup
        spec:
          skills:
            - docker-disk-cleanup
          agentRole: ops-triage-lead
          modelProfile: local-worker
          runtimeRequirements:
            - docker-readonly
        """,
    )
    write(
        pack / "agents/ops-triage-lead.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: AgentRole
        metadata:
          name: ops-triage-lead
        spec:
          purpose: Coordinate safe local ops diagnosis.
        """,
    )
    write(
        pack / "models/local-worker.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: ModelProfile
        metadata:
          name: local-worker
        spec:
          intent: Execute known workflows with a local or low-cost worker model.
        """,
    )
    write(
        pack / "runtime-requirements/docker-readonly.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: RuntimeRequirement
        metadata:
          name: docker-readonly
        spec:
          capabilities:
            - docker.read
        """,
    )
    write(
        pack / "evals/docker-disk-cleanup.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: Eval
        metadata:
          name: docker-disk-cleanup-basic
        spec:
          prompt: Diagnose why Docker is using too much disk space.
        """,
    )
    return pack


def test_load_pack_discovers_core_artifacts(tmp_path: Path) -> None:
    pack_dir = create_docker_cleanup_pack(tmp_path)

    pack = load_pack(pack_dir)

    assert pack.name == "docker-disk-cleanup"
    assert pack.skills == ["docker-disk-cleanup"]
    assert pack.workflows == ["docker-disk-cleanup"]
    assert pack.agent_roles == ["ops-triage-lead"]
    assert pack.model_profiles == ["local-worker"]
    assert pack.runtime_requirements == ["docker-readonly"]
    assert pack.evals == ["docker-disk-cleanup-basic"]


def test_generate_hermes_adapter_materializes_hermes_skills_and_instructions(tmp_path: Path) -> None:
    pack_dir = create_docker_cleanup_pack(tmp_path)
    pack = load_pack(pack_dir)
    output_dir = tmp_path / "hermes-output"

    result = generate_hermes_adapter(pack, output_dir)

    skill_file = output_dir / "skills/docker-disk-cleanup/SKILL.md"
    command_file = output_dir / "commands/docker-disk-cleanup.md"

    assert result.runtime == "hermes"
    assert skill_file.exists()
    assert command_file.exists()
    assert "Docker Disk Cleanup" in skill_file.read_text(encoding="utf-8")
    assert "Use the `docker-disk-cleanup` skill" in command_file.read_text(encoding="utf-8")
    assert "ops-triage-lead" in command_file.read_text(encoding="utf-8")

    manifest_file = output_dir / "aoh-hermes.json"
    assert manifest_file.exists()
    assert '"runtime": "hermes"' in manifest_file.read_text(encoding="utf-8")


def test_validate_pack_rejects_workflow_references_to_missing_artifacts(tmp_path: Path) -> None:
    pack_dir = create_docker_cleanup_pack(tmp_path)
    workflow = pack_dir / "workflows/docker-disk-cleanup.yaml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("docker-readonly", "missing-runtime"),
        encoding="utf-8",
    )

    pack = load_pack(pack_dir)

    try:
        validate_pack(pack)
    except PackError as exc:
        assert "missing runtime requirement `missing-runtime`" in str(exc)
    else:
        raise AssertionError("validate_pack should reject unresolved workflow references")

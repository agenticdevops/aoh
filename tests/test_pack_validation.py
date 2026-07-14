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
        apiVersion: openagentix.io/v1alpha2
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
        pack / "roles/ops-triage-lead.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Role
        metadata:
          name: ops-triage-lead
        spec:
          purpose: Coordinate safe local ops diagnosis.
        """,
    )
    write(
        pack / "models/local-worker.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
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
        apiVersion: openagentix.io/v1alpha2
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
        apiVersion: openagentix.io/v1alpha2
        kind: Eval
        metadata:
          name: docker-disk-cleanup-basic
        spec:
          skill: docker-disk-cleanup
          prompt: Diagnose why Docker is using too much disk space.
        """,
    )
    return pack


def test_load_pack_discovers_core_artifacts(tmp_path: Path) -> None:
    pack_dir = create_docker_cleanup_pack(tmp_path)

    pack = load_pack(pack_dir)

    assert pack.name == "docker-disk-cleanup"
    assert pack.skills == ["docker-disk-cleanup"]
    assert pack.roles == ["ops-triage-lead"]
    assert pack.model_profiles == ["local-worker"]
    assert pack.runtime_requirements == ["docker-readonly"]
    assert pack.evals == ["docker-disk-cleanup-basic"]


def test_generate_hermes_adapter_materializes_hermes_skills_and_instructions(tmp_path: Path) -> None:
    pack_dir = create_docker_cleanup_pack(tmp_path)
    pack = load_pack(pack_dir)
    output_dir = tmp_path / "hermes-output"

    result = generate_hermes_adapter(pack, output_dir)

    skill_file = output_dir / "skills/docker-disk-cleanup/SKILL.md"
    command_file = output_dir / "commands/ops-docker-disk-cleanup.md"

    assert result.runtime == "hermes"
    assert skill_file.exists()
    assert command_file.exists()
    assert "Docker Disk Cleanup" in skill_file.read_text(encoding="utf-8")
    assert "Use the `docker-disk-cleanup` skill" in command_file.read_text(encoding="utf-8")
    assert "ops-triage-lead" in command_file.read_text(encoding="utf-8")

    manifest_file = output_dir / "aoh-hermes.json"
    assert manifest_file.exists()
    assert '"runtime": "hermes"' in manifest_file.read_text(encoding="utf-8")


def create_skills_only_pack(root: Path) -> Path:
    pack = root / "minimal-pack"
    write(
        pack / "AOH.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Pack
        metadata:
          name: minimal-pack
        """,
    )
    write(
        pack / "skills/service-health-report/SKILL.md",
        """
        ---
        name: service-health-report
        description: Use when summarizing the health of a service from logs and metrics.
        ---

        # Service Health Report
        """,
    )
    return pack


def test_validate_pack_accepts_skills_only_pack(tmp_path: Path) -> None:
    pack = load_pack(create_skills_only_pack(tmp_path))

    validate_pack(pack)


def test_validate_pack_requires_at_least_one_skill(tmp_path: Path) -> None:
    pack_dir = create_skills_only_pack(tmp_path)
    skill_file = pack_dir / "skills/service-health-report/SKILL.md"
    skill_file.unlink()

    pack = load_pack(pack_dir)

    try:
        validate_pack(pack)
    except PackError as exc:
        assert "at least one skill" in str(exc)
    else:
        raise AssertionError("validate_pack should require at least one skill")


def test_load_pack_rejects_stale_workflows_dir(tmp_path: Path) -> None:
    pack_dir = create_skills_only_pack(tmp_path)
    write(
        pack_dir / "workflows/old.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Workflow
        metadata:
          name: old
        spec:
          skills: []
        """,
    )

    try:
        load_pack(pack_dir)
    except PackError as exc:
        assert "workflows/ is no longer supported" in str(exc)
    else:
        raise AssertionError("load_pack should reject packs with a workflows/ dir")


def test_validate_pack_requires_eval_skill(tmp_path: Path) -> None:
    pack_dir = create_skills_only_pack(tmp_path)
    write(
        pack_dir / "evals/health-basic.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Eval
        metadata:
          name: health-basic
        spec:
          prompt: Summarize service health.
        """,
    )

    pack = load_pack(pack_dir)

    try:
        validate_pack(pack)
    except PackError as exc:
        assert "Eval `health-basic` spec.skill is required" in str(exc)
    else:
        raise AssertionError("validate_pack should require eval spec.skill")


def test_load_pack_rejects_stale_agents_dir(tmp_path: Path) -> None:
    pack_dir = create_skills_only_pack(tmp_path)
    write(
        pack_dir / "agents/ops-triage-lead.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: AgentRole
        metadata:
          name: ops-triage-lead
        spec:
          purpose: Old-style role.
        """,
    )

    try:
        load_pack(pack_dir)
    except PackError as exc:
        assert "agents/ was renamed to roles/" in str(exc)
    else:
        raise AssertionError("load_pack should reject packs with an agents/ dir")


def test_load_pack_discovers_roles_dir_with_kind_role(tmp_path: Path) -> None:
    pack_dir = create_skills_only_pack(tmp_path)
    write(
        pack_dir / "roles/ops-triage-lead.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Role
        metadata:
          name: ops-triage-lead
        spec:
          purpose: Coordinate safe ops diagnosis.
          skills:
            - service-health-report
        """,
    )

    pack = load_pack(pack_dir)

    assert pack.roles == ["ops-triage-lead"]


def test_validate_pack_rejects_eval_referencing_missing_skill(tmp_path: Path) -> None:
    pack_dir = create_skills_only_pack(tmp_path)
    write(
        pack_dir / "evals/health-basic.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Eval
        metadata:
          name: health-basic
        spec:
          skill: nonexistent-skill
          prompt: Summarize service health.
        """,
    )

    pack = load_pack(pack_dir)

    try:
        validate_pack(pack)
    except PackError as exc:
        assert "Eval `health-basic` references missing skill `nonexistent-skill`" in str(exc)
    else:
        raise AssertionError("validate_pack should reject eval with missing skill ref")


def test_load_pack_rejects_v1alpha1_with_migration_pointer(tmp_path: Path) -> None:
    pack_dir = tmp_path / "old-pack"
    old_api = "openagentix.io/v1alpha" + "1"  # concatenated so the migration sed skips it
    write(
        pack_dir / "AOH.yaml",
        f"""
        apiVersion: {old_api}
        kind: Pack
        metadata:
          name: old-pack
        """,
    )
    write(
        pack_dir / "skills/service-health-report/SKILL.md",
        """
        ---
        name: service-health-report
        description: Use when summarizing the health of a service.
        ---

        # Service Health Report
        """,
    )

    try:
        load_pack(pack_dir)
    except PackError as exc:
        assert "no longer supported" in str(exc)
        assert "migration" in str(exc)
    else:
        raise AssertionError("load_pack should reject v1alpha1 packs")

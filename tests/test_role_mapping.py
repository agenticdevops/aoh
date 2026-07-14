from pathlib import Path
import sys
import textwrap


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters.hermes import install_hermes_agent
from aoh.pack import load_pack, load_role


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def create_multi_role_pack(root: Path) -> Path:
    pack = root / "acme-platform-ops"
    write(
        pack / "AOH.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Pack
        metadata:
          name: acme-platform-ops
          org: acme
          project: platform
        """,
    )
    for skill in ["docker-disk-cleanup", "service-health-report", "ml-training-job-triage"]:
        write(
            pack / f"skills/{skill}/SKILL.md",
            f"""
            ---
            name: {skill}
            description: Use when performing {skill.replace("-", " ")}.
            ---

            # {skill}
            """,
        )
    write(
        pack / "roles/sre-platform.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Role
        metadata:
          name: sre-platform
          displayName: SRE - Acme Platform
        spec:
          org: acme
          project: platform
          purpose: Own platform reliability and incident triage.
          skills:
            - docker-disk-cleanup
            - service-health-report
          runtimeRequirements:
            - shell-readonly
          modelProfile: local-worker
          responsibilities:
            - diagnose platform health
            - recommend safe remediation
        """,
    )
    write(
        pack / "roles/mlops-training.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Role
        metadata:
          name: mlops-training
        spec:
          org: acme
          project: ml-platform
          purpose: Own model training job operations.
          skills:
            - ml-training-job-triage
          runtimeRequirements:
            - shell-readonly
          modelProfile: local-worker
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
          intent: Execute known workflows with a worker model.
        """,
    )
    write(
        pack / "runtime-requirements/shell-readonly.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: RuntimeRequirement
        metadata:
          name: shell-readonly
        spec:
          capabilities:
            - shell.read
        """,
    )
    write(
        pack / "evals/sre-basic.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Eval
        metadata:
          name: sre-basic
        spec:
          skill: service-health-report
          prompt: Diagnose platform health.
        """,
    )
    return pack


def test_role_declares_project_scoped_capabilities(tmp_path: Path) -> None:
    pack = load_pack(create_multi_role_pack(tmp_path))

    role = load_role(pack, "sre-platform")

    assert role.name == "sre-platform"
    assert role.display_name == "SRE - Acme Platform"
    assert role.org == "acme"
    assert role.project == "platform"
    assert role.skills == ["docker-disk-cleanup", "service-health-report"]


def test_hermes_agent_install_can_be_scoped_to_a_role(tmp_path: Path) -> None:
    pack = load_pack(create_multi_role_pack(tmp_path))

    install_hermes_agent(
        pack,
        tmp_path / "profiles",
        profile_name="acme-platform-sre",
        provider="openai-codex",
        model="gpt-5.4",
        cwd="/tmp/acme",
        role_name="sre-platform",
    )

    profile = tmp_path / "profiles/acme-platform-sre"
    launch = profile.joinpath("launch.sh").read_text(encoding="utf-8")
    soul = profile.joinpath("SOUL.md").read_text(encoding="utf-8")

    assert profile.joinpath("skills/aoh/docker-disk-cleanup/SKILL.md").exists()
    assert profile.joinpath("skills/aoh/service-health-report/SKILL.md").exists()
    assert not profile.joinpath("skills/aoh/ml-training-job-triage/SKILL.md").exists()
    assert "--skills docker-disk-cleanup,service-health-report" in launch
    assert "SRE - Acme Platform" in soul
    assert "Own platform reliability and incident triage." in soul
    assert "Workflows:" not in soul

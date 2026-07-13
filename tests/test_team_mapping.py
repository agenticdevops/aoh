from pathlib import Path
import sys
import textwrap


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters.hermes import install_hermes_team
from aoh.pack import load_pack, load_team


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def create_team_pack(root: Path) -> Path:
    pack = root / "acme-platform-ops"
    write(
        pack / "AOH.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: Pack
        metadata:
          name: acme-platform-ops
        """,
    )
    for skill in ["service-health-report", "deployment-automation"]:
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
        pack / "workflows/platform-sre-triage.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: Workflow
        metadata:
          name: platform-sre-triage
        spec:
          skills:
            - service-health-report
          agentRole: sre-platform
          modelProfile: worker-codex
          runtimeRequirements:
            - shell-readonly
          evals:
            - platform-basic
        """,
    )
    write(
        pack / "workflows/devops-release-automation.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: Workflow
        metadata:
          name: devops-release-automation
        spec:
          skills:
            - deployment-automation
          agentRole: devops-automation
          modelProfile: worker-codex
          runtimeRequirements:
            - shell-readonly
          evals:
            - platform-basic
        """,
    )
    write(
        pack / "agents/sre-platform.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: AgentRole
        metadata:
          name: sre-platform
          displayName: SRE - Acme Platform
        spec:
          org: acme
          project: platform
          purpose: Own reliability.
          skills:
            - service-health-report
          workflows:
            - platform-sre-triage
          runtimeRequirements:
            - shell-readonly
          modelProfile: worker-codex
        """,
    )
    write(
        pack / "agents/devops-automation.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: AgentRole
        metadata:
          name: devops-automation
          displayName: DevOps Engineer - Acme Platform
        spec:
          org: acme
          project: platform
          purpose: Own release automation.
          skills:
            - deployment-automation
          workflows:
            - devops-release-automation
          runtimeRequirements:
            - shell-readonly
          modelProfile: worker-codex
        """,
    )
    write(
        pack / "teams/platform-ops.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: Team
        metadata:
          name: platform-ops
          displayName: Acme Platform Ops
        spec:
          org: acme
          businessUnit: engineering
          project: platform
          purpose: Operate the Acme platform.
          roles:
            - sre-platform
            - devops-automation
          defaultModelProfile: worker-codex
        """,
    )
    write(
        pack / "models/worker-codex.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: ModelProfile
        metadata:
          name: worker-codex
        spec:
          provider: openai-codex
          model: gpt-5.4
        """,
    )
    write(
        pack / "runtime-requirements/shell-readonly.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: RuntimeRequirement
        metadata:
          name: shell-readonly
        spec:
          capabilities:
            - shell.read
        """,
    )
    write(
        pack / "evals/platform-basic.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: Eval
        metadata:
          name: platform-basic
        spec:
          prompt: Validate platform ops behavior.
        """,
    )
    return pack


def test_team_groups_project_roles(tmp_path: Path) -> None:
    pack = load_pack(create_team_pack(tmp_path))

    team = load_team(pack, "platform-ops")

    assert team.name == "platform-ops"
    assert team.display_name == "Acme Platform Ops"
    assert team.org == "acme"
    assert team.business_unit == "engineering"
    assert team.project == "platform"
    assert team.roles == ["sre-platform", "devops-automation"]


def test_hermes_team_install_creates_one_profile_per_role(tmp_path: Path) -> None:
    pack = load_pack(create_team_pack(tmp_path))

    result = install_hermes_team(
        pack,
        tmp_path / "profiles",
        team_name="platform-ops",
        profile_prefix="acme-platform",
        provider="openai-codex",
        model="gpt-5.4",
        cwd="/tmp/acme",
    )

    assert result.runtime == "hermes"
    assert (tmp_path / "profiles/acme-platform-sre-platform/launch.sh").exists()
    assert (tmp_path / "profiles/acme-platform-devops-automation/launch.sh").exists()
    assert (
        tmp_path
        / "profiles/acme-platform-sre-platform/skills/aoh/service-health-report/SKILL.md"
    ).exists()
    assert not (
        tmp_path
        / "profiles/acme-platform-sre-platform/skills/aoh/deployment-automation/SKILL.md"
    ).exists()

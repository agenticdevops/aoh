from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.cli import main
from aoh.pack import load_pack, validate_pack


def test_init_pack_creates_valid_starter_pack(tmp_path: Path) -> None:
    pack_dir = tmp_path / "packs" / "postgres-health-check"

    exit_code = main(
        [
            "init-pack",
            "postgres-health-check",
            "--output",
            str(pack_dir),
            "--description",
            "Check PostgreSQL health using read-only diagnostics.",
        ]
    )

    assert exit_code == 0
    assert (pack_dir / "AOH.yaml").exists()
    assert (pack_dir / "skills/postgres-health-check/SKILL.md").exists()

    pack = load_pack(pack_dir)
    validate_pack(pack)

    assert pack.name == "postgres-health-check"
    assert pack.skills == ["postgres-health-check"]


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

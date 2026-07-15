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

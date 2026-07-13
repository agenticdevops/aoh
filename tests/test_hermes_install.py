from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters.hermes import install_hermes_pack
from aoh.pack import load_pack


def test_install_hermes_pack_copies_skill_into_category_and_adds_aoh_reference(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/docker-disk-cleanup")
    skills_dir = tmp_path / "hermes-skills"

    result = install_hermes_pack(pack, skills_dir, category="aoh")

    installed_skill = skills_dir / "aoh/docker-disk-cleanup/SKILL.md"
    workflow_reference = skills_dir / "aoh/docker-disk-cleanup/references/aoh-workflow.md"

    assert result.runtime == "hermes"
    assert installed_skill.exists()
    assert workflow_reference.exists()
    assert "Docker Disk Cleanup" in installed_skill.read_text(encoding="utf-8")
    assert "docker-disk-cleanup" in workflow_reference.read_text(encoding="utf-8")

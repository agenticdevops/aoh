from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters.hermes import generate_hermes_adapter
from aoh.pack import load_pack


def test_core_docker_disk_cleanup_pack_is_valid(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/docker-disk-cleanup")

    assert pack.name == "docker-disk-cleanup"
    assert pack.skills == ["docker-disk-cleanup"]
    assert pack.workflows == []

    result = generate_hermes_adapter(pack, tmp_path / "hermes")

    assert result.runtime == "hermes"
    assert (tmp_path / "hermes/skills/docker-disk-cleanup/SKILL.md").exists()

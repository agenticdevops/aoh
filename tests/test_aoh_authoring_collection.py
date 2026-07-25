import stat
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.pack import load_pack, validate_pack


def test_aoh_authoring_pack_is_valid() -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/aoh-authoring")

    assert pack.name == "aoh-authoring"
    assert pack.skills == ["author-and-promote-skill"]

    validate_pack(pack)


def test_author_and_promote_skill_frontmatter_matches_dir() -> None:
    skill_md = (
        PROJECT_ROOT
        / "collections/core/aoh-authoring/skills/author-and-promote-skill/SKILL.md"
    )
    text = skill_md.read_text(encoding="utf-8")
    assert text.startswith("---")
    frontmatter = text.split("---", 2)[1]
    assert "name: author-and-promote-skill" in frontmatter
    assert "description:" in frontmatter


def test_author_and_promote_skill_script_is_executable() -> None:
    script = (
        PROJECT_ROOT
        / "collections/core/aoh-authoring/skills/author-and-promote-skill"
        / "scripts/promote.sh"
    )
    assert script.exists()
    mode = script.stat().st_mode
    assert mode & stat.S_IXUSR, "scripts/promote.sh must be executable"


def test_docker_disk_cleanup_pack_still_valid_regression() -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/docker-disk-cleanup")
    assert pack.name == "docker-disk-cleanup"


def test_kubeops_pack_still_valid_regression() -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")
    validate_pack(pack)
    assert pack.name == "kubeops"

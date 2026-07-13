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
    assert (pack_dir / "workflows/postgres-health-check.yaml").exists()

    pack = load_pack(pack_dir)
    validate_pack(pack)

    assert pack.name == "postgres-health-check"
    assert pack.skills == ["postgres-health-check"]

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters.hermes import install_hermes_agent
from aoh.pack import load_pack


def test_install_hermes_agent_creates_profile_with_skill_and_launcher(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/docker-disk-cleanup")
    profiles_dir = tmp_path / "profiles"

    result = install_hermes_agent(
        pack,
        profiles_dir,
        profile_name="aoh-docker-disk-cleanup",
        provider="openai-codex",
        model="gpt-5.4",
        cwd="/tmp",
    )

    profile_dir = profiles_dir / "aoh-docker-disk-cleanup"
    assert result.runtime == "hermes"
    assert profile_dir.joinpath("config.yaml").exists()
    assert profile_dir.joinpath("SOUL.md").exists()
    assert profile_dir.joinpath("skills/aoh/docker-disk-cleanup/SKILL.md").exists()
    assert profile_dir.joinpath("aoh-agent.json").exists()
    assert profile_dir.joinpath("launch.sh").exists()

    config = profile_dir.joinpath("config.yaml").read_text(encoding="utf-8")
    soul = profile_dir.joinpath("SOUL.md").read_text(encoding="utf-8")
    launch = profile_dir.joinpath("launch.sh").read_text(encoding="utf-8")

    assert "provider: openai-codex" in config
    assert "default: gpt-5.4" in config
    assert "AOH custom Hermes agent" in soul
    assert "--profile aoh-docker-disk-cleanup" in launch
    assert "--skills docker-disk-cleanup" in launch

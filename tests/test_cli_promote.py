from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.cli import main


# ---------------------------------------------------------------------------
# fixture helpers (mirrors tests/test_promote.py conventions)
# ---------------------------------------------------------------------------


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _seed_minimal_pack(work: Path) -> None:
    write(
        work / "AOH.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Pack
        metadata:
          name: demo
          displayName: Demo
          description: Minimal demo pack for promote CLI tests.
          owner: Test
        """,
    )
    write(
        work / "skills" / "existing-skill" / "SKILL.md",
        """
        ---
        name: existing-skill
        description: Use when demoing promote CLI's existing pack content.
        ---

        # Existing Skill

        Placeholder body.
        """,
    )


def make_bare_repo(tmp_path: Path, name: str = "origin.git") -> Path:
    bare = tmp_path / name
    _run(["git", "init", "--bare", "-q", str(bare)], cwd=tmp_path)

    work = tmp_path / f"_seed-{name}"
    _run(["git", "init", "-q", str(work)], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "Test"], cwd=work)

    _seed_minimal_pack(work)

    _run(["git", "add", "-A"], cwd=work)
    _run(["git", "commit", "-q", "-m", "seed"], cwd=work)
    _run(["git", "remote", "add", "origin", str(bare)], cwd=work)
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)

    return bare


def bare_repo_url(bare: Path) -> str:
    return f"file://{bare}"


def make_draft(tmp_path: Path, name: str = "foo") -> Path:
    draft = tmp_path / "draft" / name
    write(
        draft / "SKILL.md",
        f"""
        ---
        name: {name}
        description: Use when testing the promote CLI with {name}.
        ---

        # {name}

        Draft skill body.
        """,
    )
    script = draft / "scripts" / "run.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    script.chmod(0o755)
    return draft


def _configure_pack(aoh_home: Path, name: str, repo_url: str) -> None:
    assert main(["config", "set", f"packs.{name}.repo", repo_url]) == 0


def _log_count(bare: Path) -> int:
    result = _run(["git", "log", "--oneline"], cwd=bare)
    return len(result.stdout.strip().splitlines())


def make_broken_draft(tmp_path: Path, name: str = "broken-skill") -> Path:
    """Draft whose SKILL.md frontmatter name does not match the dir name —
    a validation failure the pack loader catches in the worktree, distinct
    from PromoteError/GitOpsError/SkillCopyError."""
    draft = tmp_path / "draft-broken" / name
    write(
        draft / "SKILL.md",
        f"""
        ---
        name: totally-different-name
        description: Use when testing broken frontmatter via the CLI.
        ---

        # {name}

        Draft skill body with mismatched frontmatter name.
        """,
    )
    return draft


# ---------------------------------------------------------------------------
# aoh skill promote
# ---------------------------------------------------------------------------


def test_skill_promote_happy_path_direct_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    aoh_home = tmp_path / ".aoh"
    monkeypatch.setenv("AOH_HOME", str(aoh_home))

    bare = make_bare_repo(tmp_path)
    _configure_pack(aoh_home, "testpack", bare_repo_url(bare))

    draft = make_draft(tmp_path, name="foo")

    exit_code = main(
        [
            "skill",
            "promote",
            "foo",
            "--from",
            str(draft),
            "--pack",
            "testpack",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "promoted foo to testpack @" in captured.out

    clone = tmp_path / "_verify"
    _run(["git", "clone", "-q", str(bare), str(clone)], cwd=tmp_path)
    assert (clone / "skills" / "foo" / "SKILL.md").exists()


def test_skill_promote_unconfigured_pack_name_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    aoh_home = tmp_path / ".aoh"
    monkeypatch.setenv("AOH_HOME", str(aoh_home))
    assert main(["config", "init"]) == 0

    draft = make_draft(tmp_path, name="foo")

    exit_code = main(
        [
            "skill",
            "promote",
            "foo",
            "--from",
            str(draft),
            "--pack",
            "missing-pack",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "missing-pack" in captured.err
    assert "packs.missing-pack" in captured.err


def test_skill_promote_local_path_pack_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    aoh_home = tmp_path / ".aoh"
    monkeypatch.setenv("AOH_HOME", str(aoh_home))
    assert main(["config", "init"]) == 0
    assert main(["config", "set", "packs.localpack", str(tmp_path / "some-local-pack")]) == 0

    draft = make_draft(tmp_path, name="foo")

    exit_code = main(
        [
            "skill",
            "promote",
            "foo",
            "--from",
            str(draft),
            "--pack",
            "localpack",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "git-hosted" in captured.err or "git-backed" in captured.err
    assert "localpack" in captured.err


def test_skill_promote_reprepromote_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    aoh_home = tmp_path / ".aoh"
    monkeypatch.setenv("AOH_HOME", str(aoh_home))

    bare = make_bare_repo(tmp_path)
    _configure_pack(aoh_home, "testpack", bare_repo_url(bare))

    draft = make_draft(tmp_path, name="foo")

    assert main(
        ["skill", "promote", "foo", "--from", str(draft), "--pack", "testpack"]
    ) == 0
    capsys.readouterr()

    count_after_first = _log_count(bare)

    exit_code = main(
        ["skill", "promote", "foo", "--from", str(draft), "--pack", "testpack"]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "(no-op)" in captured.out

    assert _log_count(bare) == count_after_first


def test_skill_promote_pack_validation_failure_uses_pack_error_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    aoh_home = tmp_path / ".aoh"
    monkeypatch.setenv("AOH_HOME", str(aoh_home))

    bare = make_bare_repo(tmp_path)
    _configure_pack(aoh_home, "testpack", bare_repo_url(bare))

    draft = make_broken_draft(tmp_path)

    exit_code = main(
        [
            "skill",
            "promote",
            "broken-skill",
            "--from",
            str(draft),
            "--pack",
            "testpack",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    # Pack VALIDATION failures keep the existing top-level prefix, distinct
    # from promote's OPERATIONAL "promote failed:" prefix.
    assert "invalid AOH pack:" in captured.out or "invalid AOH pack:" in captured.err
    assert "promote failed:" not in captured.err

    # No commit should have landed.
    assert _log_count(bare) == 1

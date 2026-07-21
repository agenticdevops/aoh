from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.skillcopy import (
    MAX_FILE_BYTES,
    MAX_FILE_COUNT,
    MAX_TOTAL_BYTES,
    SkillCopyError,
    copy_skill_tree,
)


def _make_basic_skill(root: Path) -> Path:
    skill_dir = root / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\ndescription: demo\n---\nBody.\n")
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    script = scripts_dir / "foo.sh"
    script.write_text("#!/bin/sh\necho hi\n")
    script.chmod(0o755)
    return skill_dir


# --- happy path ---


def test_copy_skill_tree_happy_path_preserves_executable_bit(tmp_path: Path) -> None:
    src = _make_basic_skill(tmp_path / "src")
    dest = tmp_path / "dest"

    copied = copy_skill_tree(src, dest)

    assert (dest / "SKILL.md").exists()
    assert (dest / "scripts" / "foo.sh").exists()
    mode = os.stat(dest / "scripts" / "foo.sh").st_mode
    assert mode & 0o111, "executable bit should be preserved by copy2"


def test_copy_skill_tree_returns_sorted_relative_posix_paths(tmp_path: Path) -> None:
    src = _make_basic_skill(tmp_path / "src")
    dest = tmp_path / "dest"

    copied = copy_skill_tree(src, dest)

    assert copied == sorted(copied)
    assert "SKILL.md" in copied
    assert "scripts/foo.sh" in copied
    # posix-style forward slashes, never backslashes
    assert all("\\" not in p for p in copied)


# --- .git rejection ---


def test_copy_skill_tree_rejects_nested_git_dir(tmp_path: Path) -> None:
    src = _make_basic_skill(tmp_path / "src")
    nested = src / "sub" / ".git"
    nested.mkdir(parents=True)
    (nested / "config").write_text("[core]\n")
    dest = tmp_path / "dest"

    with pytest.raises(SkillCopyError):
        copy_skill_tree(src, dest)

    assert not dest.exists()


def test_copy_skill_tree_rejects_git_dir_at_root(tmp_path: Path) -> None:
    src = _make_basic_skill(tmp_path / "src")
    (src / ".git").mkdir()
    dest = tmp_path / "dest"

    with pytest.raises(SkillCopyError):
        copy_skill_tree(src, dest)

    assert not dest.exists()


# --- symlink rejection ---


def test_copy_skill_tree_rejects_symlink(tmp_path: Path) -> None:
    src = _make_basic_skill(tmp_path / "src")
    target = tmp_path / "outside.txt"
    target.write_text("hello")
    link = src / "scripts" / "sneaky-link"
    link.symlink_to(target)
    dest = tmp_path / "dest"

    with pytest.raises(SkillCopyError):
        copy_skill_tree(src, dest)

    assert not dest.exists()


def test_copy_skill_tree_rejects_symlinked_directory(tmp_path: Path) -> None:
    src = _make_basic_skill(tmp_path / "src")
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    link = src / "linked-dir"
    link.symlink_to(outside_dir, target_is_directory=True)
    dest = tmp_path / "dest"

    with pytest.raises(SkillCopyError):
        copy_skill_tree(src, dest)

    assert not dest.exists()


# --- device / socket / fifo rejection ---


def test_copy_skill_tree_rejects_fifo(tmp_path: Path) -> None:
    src = _make_basic_skill(tmp_path / "src")
    fifo_path = src / "scripts" / "a-fifo"
    os.mkfifo(fifo_path)
    dest = tmp_path / "dest"

    with pytest.raises(SkillCopyError):
        copy_skill_tree(src, dest)

    assert not dest.exists()


# --- oversized file rejection ---


def test_copy_skill_tree_rejects_oversized_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aoh.skillcopy.MAX_FILE_BYTES", 16)
    src = _make_basic_skill(tmp_path / "src")
    big_file = src / "too-big.bin"
    big_file.write_bytes(b"x" * 32)
    dest = tmp_path / "dest"

    with pytest.raises(SkillCopyError):
        copy_skill_tree(src, dest)

    assert not dest.exists()


# --- file count limit ---


def test_copy_skill_tree_rejects_too_many_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aoh.skillcopy.MAX_FILE_COUNT", 3)
    src = _make_basic_skill(tmp_path / "src")
    for i in range(5):
        (src / f"extra-{i}.txt").write_text("x")
    dest = tmp_path / "dest"

    with pytest.raises(SkillCopyError):
        copy_skill_tree(src, dest)

    assert not dest.exists()


# --- total size limit ---


def test_copy_skill_tree_rejects_over_total_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aoh.skillcopy.MAX_TOTAL_BYTES", 20)
    src = _make_basic_skill(tmp_path / "src")
    (src / "a.bin").write_bytes(b"x" * 12)
    (src / "b.bin").write_bytes(b"x" * 12)
    dest = tmp_path / "dest"

    with pytest.raises(SkillCopyError):
        copy_skill_tree(src, dest)

    assert not dest.exists()


def test_copy_skill_tree_dest_must_not_already_exist(tmp_path: Path) -> None:
    src = _make_basic_skill(tmp_path / "src")
    dest = tmp_path / "dest"
    dest.mkdir()

    with pytest.raises(SkillCopyError):
        copy_skill_tree(src, dest)

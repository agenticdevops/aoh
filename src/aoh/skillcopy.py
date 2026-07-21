from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

from aoh.paths import safe_join

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MiB per file
MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MiB per skill
MAX_FILE_COUNT = 500


class SkillCopyError(ValueError):
    """Raised when a skill source tree fails the copy-hygiene checks."""


def copy_skill_tree(src: Path, dest: Path) -> list[str]:
    """Copy `src` (a skill directory) onto `dest` (must not already exist).

    Walks `src` and for EVERY entry:
      - a directory named `.git` anywhere -> refused (whole copy aborted)
      - a symlink -> refused
      - a device/socket/fifo -> refused
      - a regular file exceeding MAX_FILE_BYTES -> refused
    Also enforces MAX_FILE_COUNT and MAX_TOTAL_BYTES across the whole tree.

    All checks happen in a single pre-scan pass BEFORE anything is copied,
    so any violation leaves `dest` completely untouched (no partial copy).
    Returns the sorted list of copied relative paths (posix-style).
    """
    if dest.exists():
        raise SkillCopyError(f"destination already exists: {dest}")

    relative_files = _scan(src)

    for rel in relative_files:
        # Defense in depth: validate every destination write path through
        # safe_join, even though `src` was walked via os.walk (not attacker
        # controlled globbing).
        safe_join(dest, *rel.parts)

    dest.mkdir(parents=True)
    copied: list[str] = []
    for rel in relative_files:
        dest_path = safe_join(dest, *rel.parts)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, dest_path)
        copied.append(rel.as_posix())

    return sorted(copied)


def _scan(src: Path) -> list[Path]:
    """Pre-scan the whole tree, validating hygiene and limits.

    Returns the list of relative file paths to copy. Raises SkillCopyError
    on the first violation found, without copying anything.
    """
    relative_files: list[Path] = []
    total_bytes = 0
    file_count = 0

    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        dir_path = Path(dirpath)

        # Check subdirectories for .git and symlinked directories before
        # descending into them.
        for dirname in dirnames:
            entry = dir_path / dirname
            if dirname == ".git":
                raise SkillCopyError(f"refused: `.git` directory found at {entry}")
            if entry.is_symlink():
                raise SkillCopyError(f"refused: symlink found at {entry}")

        for filename in filenames:
            entry = dir_path / filename
            st = entry.lstat()

            if stat.S_ISLNK(st.st_mode):
                raise SkillCopyError(f"refused: symlink found at {entry}")
            if stat.S_ISBLK(st.st_mode) or stat.S_ISCHR(st.st_mode):
                raise SkillCopyError(f"refused: device file found at {entry}")
            if stat.S_ISSOCK(st.st_mode):
                raise SkillCopyError(f"refused: socket found at {entry}")
            if stat.S_ISFIFO(st.st_mode):
                raise SkillCopyError(f"refused: fifo found at {entry}")
            if not stat.S_ISREG(st.st_mode):
                raise SkillCopyError(f"refused: unsupported file type at {entry}")

            if st.st_size > MAX_FILE_BYTES:
                raise SkillCopyError(
                    f"refused: file {entry} exceeds MAX_FILE_BYTES ({st.st_size} > {MAX_FILE_BYTES})"
                )

            file_count += 1
            if file_count > MAX_FILE_COUNT:
                raise SkillCopyError(
                    f"refused: skill tree has more than MAX_FILE_COUNT ({MAX_FILE_COUNT}) files"
                )

            total_bytes += st.st_size
            if total_bytes > MAX_TOTAL_BYTES:
                raise SkillCopyError(
                    f"refused: skill tree exceeds MAX_TOTAL_BYTES ({total_bytes} > {MAX_TOTAL_BYTES})"
                )

            relative_files.append(entry.relative_to(src))

    return relative_files

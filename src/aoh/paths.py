from __future__ import annotations

import re
from pathlib import Path

from aoh.pack import PackError

_SEGMENT_RE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")


def safe_segment(kind: str, value: str) -> str:
    """Validate `value` as a single safe path segment.

    Must match ^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$ — lowercase alphanumerics
    and internal hyphens only, 1-63 chars, no leading/trailing hyphen, no
    path separators, no `..`. Raises PackError (naming `kind`) otherwise.
    """
    if not isinstance(value, str) or not _SEGMENT_RE.match(value):
        raise PackError(f"Invalid {kind} name `{value}`: must match {_SEGMENT_RE.pattern}")
    return value


def safe_join(root: Path, *segments: str) -> Path:
    """Join `segments` onto `root`, rejecting anything that could escape it.

    Each segment must be non-empty, must not contain a path separator, and
    must not be `..`. The resolved result must remain under root.resolve()
    (symlink escapes included) or PackError is raised.
    """
    resolved_root = root.resolve()
    result = resolved_root
    for segment in segments:
        if not segment:
            raise PackError(f"Invalid path segment: empty segment in {segments!r}")
        if "/" in segment or "\\" in segment:
            raise PackError(f"Invalid path segment `{segment}`: must not contain a path separator")
        if segment in (".", ".."):
            raise PackError(f"Invalid path segment `{segment}`: must not be '.' or '..'")
        if Path(segment).is_absolute():
            raise PackError(f"Invalid path segment `{segment}`: must not be absolute")
        result = result / segment

    resolved_result = result.resolve()
    try:
        resolved_result.relative_to(resolved_root)
    except ValueError:
        raise PackError(f"Path `{result}` escapes root `{resolved_root}`") from None

    return resolved_result

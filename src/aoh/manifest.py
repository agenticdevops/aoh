"""aoh-manifest.json — per-workspace install record.

Written atomically after every convergent install (see `installer.py`).
Records what pack/binding/runtime produced the workspace, at which resolved
commit, which files AOH owns (and their content hashes), and how pack-source
files map onto materialized paths. Reading a manifest validates every
`ownedFiles` / `artifactMap` path as a safe, non-escaping, workspace-relative
path (F8) — a manifest is untrusted input once it could have been edited or
forged.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoh.pack import PackError
from aoh.paths import safe_join

MANIFEST_NAME = "aoh-manifest.json"

NAMING_SCHEME_SITE_QUALIFIED = "v2-site-qualified"
NAMING_SCHEME_LEGACY = "v1-legacy"

_VALID_NAMING_SCHEMES = {NAMING_SCHEME_SITE_QUALIFIED, NAMING_SCHEME_LEGACY}


def hash_tree(root: Path | str) -> dict[str, dict[str, Any]]:
    """Hash every regular file under `root`.

    Returns {posix-relative-path: {"sha": sha256-hex, "exec": bool}}.
    Symlinks are skipped (never treated as owned content).
    """
    root_path = Path(root)
    result: dict[str, dict[str, Any]] = {}
    if not root_path.is_dir():
        return result

    for path in sorted(root_path.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(root_path).as_posix()
        result[rel] = {
            "sha": _sha256_file(path),
            "exec": bool(path.stat().st_mode & stat.S_IXUSR),
        }
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    *,
    pack: str,
    source: dict[str, Any],
    resolved_commit: str | None,
    binding: str | None,
    runtime: str,
    adapter: str,
    naming_scheme: str,
    owned_files: list[str],
    transform_id: str,
    artifact_map: dict[str, str],
    canonical_hashes: dict[str, Any],
    materialized_hashes: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a manifest document (as a plain JSON-able dict).

    No `txn` block — that only appears transiently inside the journal, never
    in the steady-state manifest.
    """
    if naming_scheme not in _VALID_NAMING_SCHEMES:
        raise PackError(
            f"Invalid namingScheme `{naming_scheme}`: must be one of {sorted(_VALID_NAMING_SCHEMES)}"
        )

    return {
        "pack": pack,
        "source": dict(source),
        "resolvedCommit": resolved_commit,
        "binding": binding,
        "runtime": runtime,
        "adapter": adapter,
        "namingScheme": naming_scheme,
        "generatedAt": generated_at or _now_iso(),
        "ownedFiles": list(owned_files),
        "transformId": transform_id,
        "artifactMap": dict(artifact_map),
        "canonicalHashes": dict(canonical_hashes),
        "materializedHashes": dict(materialized_hashes),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_manifest(workspace: Path | str, doc: dict[str, Any]) -> Path:
    """Write the manifest atomically: write to a tmp file in the same
    directory, fsync, then os.replace onto the final name."""
    workspace_path = Path(workspace)
    workspace_path.mkdir(parents=True, exist_ok=True)
    final_path = workspace_path / MANIFEST_NAME

    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{MANIFEST_NAME}.", suffix=".tmp", dir=str(workspace_path)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, final_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise

    return final_path


def read_manifest(workspace: Path | str) -> dict[str, Any] | None:
    """Read and validate the manifest at `workspace/aoh-manifest.json`.

    Returns None if absent. Every `ownedFiles` entry and every `artifactMap`
    value (materialized-side path) is validated as a safe, non-escaping,
    workspace-relative path via `paths.safe_join` — PackError otherwise
    (F8: a manifest is untrusted input).
    """
    workspace_path = Path(workspace)
    manifest_path = workspace_path / MANIFEST_NAME
    if not manifest_path.exists():
        return None

    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest_paths(workspace_path, doc)
    return doc


def _validate_manifest_paths(workspace: Path, doc: dict[str, Any]) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    for rel in doc.get("ownedFiles", []):
        _validate_rel_path(workspace, rel, "ownedFiles")
    for canonical, materialized in doc.get("artifactMap", {}).items():
        _validate_rel_path(workspace, materialized, f"artifactMap[{canonical}]")


def _validate_rel_path(workspace: Path, rel: str, context: str) -> None:
    if not isinstance(rel, str) or not rel:
        raise PackError(f"Invalid manifest path in {context}: {rel!r}")
    segments = rel.split("/")
    try:
        safe_join(workspace, *segments)
    except PackError as exc:
        raise PackError(f"Invalid manifest path in {context}: {rel!r}: {exc}") from None

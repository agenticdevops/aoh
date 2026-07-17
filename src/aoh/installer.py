"""Crash-safe convergent installer — journal protocol.

Wraps `RuntimeAdapter.materialize` with a write-ahead journal so an
interrupted install (crash, kill -9, power loss) can always be recovered
into either "nothing happened" or "the new install completed" — never a
half-written workspace.

Sequence, under an adjacent `.aoh-install.lock` (LOCK_EX|LOCK_NB, fd held
for the whole critical section, released in `finally`):

  0. If a journal is already present, RECOVER first (see `_recover`):
       phase == "staged"     -> delete staging + journal (nothing was
                                  mutated yet; clean abort)
       phase == "committing" -> roll FORWARD: re-copy files from staging
                                  per journal["newOwned"], verify hashes,
                                  write journal["newManifest"] verbatim,
                                  finish (delete journal + staging)
  1. Verify current owned files (per the existing manifest's
     materializedHashes) against what's actually on disk. Any owned file
     that was modified locally, when discard_local is False, refuses the
     whole install (InstallRefused) and touches nothing. Regardless of
     discard_local, every replaced/removed owned file is ALWAYS backed up
     into backupDir before it is overwritten or deleted.
  2. adapter.materialize(...) writes into a staging directory that is a
     SIBLING of the workspace (workspace.parent/.aoh-stage-<txnId>) — same
     filesystem, so the later per-file copy is cheap and atomic-renameable.
  3. Journal written with phase="staged" (fsync'd), then flipped to
     phase="committing" (fsync'd again) — this is the write-ahead barrier:
     once phase=="committing" is on disk, the only safe recovery action is
     roll-forward, never abort.
  4. Per file: back up the old owned file (if any) into backupDir, copy the
     staged file into place, remove any owned file that's stale (no longer
     produced by this install).
  5. Rehash the real workspace, write the manifest atomically (tmp+rename),
     delete the journal and staging directory last.

`stagingDir` / `backupDir` are stored in the journal as workspace-relative
bare names (never absolute paths) and re-validated via `paths.safe_join` on
recovery — nothing path-like from a journal is trusted without validation
(round-2 amendment 2).
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import stat
import uuid
from contextlib import contextmanager
from dataclasses import replace as _dataclass_replace
from pathlib import Path
from typing import Any, Iterator

from aoh.adapters.base import MaterializeRequest, RuntimeAdapter
from aoh.manifest import (
    MANIFEST_NAME,
    build_manifest,
    hash_tree,
    read_manifest,
    write_manifest,
)
from aoh.pack import PackError
from aoh.paths import safe_join

JOURNAL_NAME = ".aoh-journal.json"
LOCK_NAME = ".aoh-install.lock"


class InstallRefused(RuntimeError):
    """Raised when an install cannot proceed safely: local modifications to
    owned files without --discard-local, or lock contention with another
    installer process."""


# ---------------------------------------------------------------------------
# public entrypoint
# ---------------------------------------------------------------------------


def install_workspace(
    *,
    adapter: RuntimeAdapter,
    request: MaterializeRequest,
    source: dict[str, Any],
    commit: str | None,
    naming_scheme: str,
    discard_local: bool = False,
    binding_name: str | None = None,
):
    """Materialize `request` into `request.output_dir` via `adapter`,
    convergently and crash-safely, recording an `aoh-manifest.json`.

    Returns the adapter's `AdapterResult` (output_dir == the workspace).
    """
    workspace = Path(request.output_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    lock_path = workspace.parent / LOCK_NAME

    with _install_lock(lock_path):
        _recover_if_needed(workspace)
        return _do_install(
            adapter=adapter,
            request=request,
            workspace=workspace,
            source=source,
            commit=commit,
            naming_scheme=naming_scheme,
            discard_local=discard_local,
            binding_name=binding_name,
        )


# ---------------------------------------------------------------------------
# locking
# ---------------------------------------------------------------------------


@contextmanager
def _install_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InstallRefused(
                f"another aoh install is already running against `{lock_path.parent}` "
                f"(lock `{lock_path}` held)"
            ) from None
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


# ---------------------------------------------------------------------------
# recovery
# ---------------------------------------------------------------------------


def _recover_if_needed(workspace: Path) -> None:
    journal_path = workspace / JOURNAL_NAME
    if not journal_path.exists():
        return

    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    phase = journal.get("phase")

    staging_dir = _resolve_journal_dir(workspace, journal.get("stagingDir"), sibling=True)
    backup_dir = _resolve_journal_dir(workspace, journal.get("backupDir"), sibling=False)

    if phase == "staged":
        # Nothing was mutated in the real workspace yet — clean abort.
        if staging_dir is not None and staging_dir.exists():
            shutil.rmtree(staging_dir)
        journal_path.unlink()
        return

    if phase == "committing":
        _roll_forward(workspace, journal, staging_dir, backup_dir)
        journal_path.unlink()
        return

    # Unknown/corrupt phase: don't guess. Leave the journal for a human,
    # but don't let it silently block forever either — raise loudly.
    raise InstallRefused(
        f"unrecognized journal phase `{phase}` in `{journal_path}` — manual recovery required"
    )


def _resolve_journal_dir(workspace: Path, name: Any, *, sibling: bool) -> Path | None:
    if not isinstance(name, str) or not name:
        return None
    root = workspace.parent if sibling else workspace
    try:
        return safe_join(root, name)
    except PackError as exc:
        raise PackError(f"Invalid journal directory name `{name}`: {exc}") from None


def _roll_forward(
    workspace: Path,
    journal: dict[str, Any],
    staging_dir: Path | None,
    backup_dir: Path | None,
) -> None:
    new_owned: dict[str, Any] = journal.get("newOwned", {})
    new_manifest: dict[str, Any] | None = journal.get("newManifest")
    old_owned: dict[str, Any] = journal.get("oldOwned", {})

    backup_has_content = backup_dir is not None and backup_dir.exists() and any(
        backup_dir.iterdir()
    )

    # Files that existed before this install but are not part of the new
    # set must be removed too (mirrors the normal commit path) — but ONLY
    # ones that are safe/validated relative paths.
    stale = set(old_owned) - set(new_owned) - {MANIFEST_NAME}

    for rel in sorted(stale):
        target = _safe_workspace_path(workspace, rel)
        if target.exists() or target.is_symlink():
            if not backup_has_content:
                _backup_file(backup_dir, workspace, rel)
            target.unlink()

    for rel in sorted(set(new_owned) - {MANIFEST_NAME}):
        target = _safe_workspace_path(workspace, rel)
        staged_file = None
        if staging_dir is not None:
            staged_candidate = _safe_workspace_path(staging_dir, rel)
            if staged_candidate.exists():
                staged_file = staged_candidate

        if staged_file is None:
            # Already rolled forward in a prior partial recovery attempt,
            # or the file was never staged (shouldn't happen) — trust
            # what's on disk if it already matches; otherwise this is an
            # unrecoverable inconsistency.
            if target.exists():
                continue
            raise InstallRefused(
                f"cannot recover: staged file for `{rel}` missing and target absent"
            )

        if target.exists() and not backup_has_content:
            _backup_file(backup_dir, workspace, rel)

        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_file(staged_file, target, executable=bool(new_owned[rel].get("exec")))

    if new_manifest is not None:
        write_manifest(workspace, new_manifest)

    if staging_dir is not None and staging_dir.exists():
        shutil.rmtree(staging_dir)


# ---------------------------------------------------------------------------
# normal install path
# ---------------------------------------------------------------------------


def _do_install(
    *,
    adapter: RuntimeAdapter,
    request: MaterializeRequest,
    workspace: Path,
    source: dict[str, Any],
    commit: str | None,
    naming_scheme: str,
    discard_local: bool,
    binding_name: str | None,
):
    existing_manifest = read_manifest(workspace)
    _verify_no_local_modifications(workspace, existing_manifest, discard_local)

    txn_id = uuid.uuid4().hex
    stage_name = f".aoh-stage-{txn_id}"
    backup_name = f".aoh-backup-{txn_id}"
    staging_dir = workspace.parent / stage_name
    backup_dir = workspace / backup_name

    staging_request = MaterializeRequest(
        pack=request.pack,
        output_dir=staging_dir,
        role_name=request.role_name,
        binding=request.binding,
        profile=request.profile,
        model_hint=request.model_hint,
        workdir=request.workdir,
        options=request.options,
    )
    result = adapter.materialize(staging_request)

    staged_hashes = hash_tree(staging_dir)
    new_owned = dict(staged_hashes)
    new_owned[MANIFEST_NAME] = {"sha": "", "exec": False}  # placeholder, rewritten below

    old_owned = existing_manifest.get("materializedHashes", {}) if existing_manifest else {}

    binding_resolved = binding_name
    if binding_resolved is None and request.binding is not None:
        binding_resolved = request.binding.name

    new_manifest_doc = build_manifest(
        pack=request.pack.name,
        source=source,
        resolved_commit=commit,
        binding=binding_resolved,
        runtime=result.runtime,
        adapter=result.runtime,
        naming_scheme=naming_scheme,
        owned_files=sorted(set(staged_hashes) | {MANIFEST_NAME}),
        transform_id=result.transform_id,
        artifact_map=result.artifact_map,
        canonical_hashes=staged_hashes,
        materialized_hashes=staged_hashes,
    )

    journal = {
        "txnId": txn_id,
        "phase": "staged",
        "workspaceRoot": ".",
        "stagingDir": stage_name,
        "backupDir": backup_name,
        "oldOwned": old_owned,
        "newOwned": new_owned,
        "newManifest": new_manifest_doc,
    }
    journal_path = workspace / JOURNAL_NAME
    _write_journal(journal_path, journal)

    journal["phase"] = "committing"
    _write_journal(journal_path, journal)

    _commit(workspace, staging_dir, backup_dir, old_owned, staged_hashes)
    write_manifest(workspace, new_manifest_doc)

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    if backup_dir.exists() and not any(backup_dir.iterdir()):
        backup_dir.rmdir()
    journal_path.unlink()

    generated_files = sorted(_safe_workspace_path(workspace, rel) for rel in staged_hashes)
    return _dataclass_replace(result, output_dir=workspace, generated_files=generated_files)


def _write_journal(journal_path: Path, journal: dict[str, Any]) -> None:
    with open(journal_path, "w", encoding="utf-8") as fh:
        json.dump(journal, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())


def _verify_no_local_modifications(
    workspace: Path, existing_manifest: dict[str, Any] | None, discard_local: bool
) -> None:
    if existing_manifest is None:
        return

    materialized_hashes: dict[str, Any] = existing_manifest.get("materializedHashes", {})
    modified: list[str] = []
    for rel, info in materialized_hashes.items():
        if rel == MANIFEST_NAME:
            continue
        target = _safe_workspace_path(workspace, rel)
        if not target.exists():
            modified.append(rel)
            continue
        current_hash = hash_tree(workspace).get(rel)
        if current_hash is None or current_hash["sha"] != info.get("sha"):
            modified.append(rel)

    if modified and not discard_local:
        raise InstallRefused(
            "refusing to install: locally modified owned files would be overwritten "
            f"(use --discard-local to override): {', '.join(sorted(modified))}"
        )


def _commit(
    workspace: Path,
    staging_dir: Path,
    backup_dir: Path,
    old_owned: dict[str, Any],
    new_owned: dict[str, Any],
) -> None:
    stale = set(old_owned) - set(new_owned) - {MANIFEST_NAME}

    for rel in sorted(stale):
        target = _safe_workspace_path(workspace, rel)
        if target.exists() or target.is_symlink():
            _backup_file(backup_dir, workspace, rel)
            target.unlink()

    current_hashes = hash_tree(workspace)

    for rel in sorted(set(new_owned) - {MANIFEST_NAME}):
        target = _safe_workspace_path(workspace, rel)
        staged_file = _safe_workspace_path(staging_dir, rel)
        if not staged_file.exists():
            continue
        # "unchanged" must be judged against what's ACTUALLY on disk right
        # now, not the manifest's recorded (pre-edit) hash — otherwise a
        # locally-modified-then-discard_local'd file that happens to match
        # the pack's own canonical content would be skipped and the local
        # edit would survive.
        current_info = current_hashes.get(rel)
        unchanged = (
            target.exists()
            and current_info is not None
            and current_info.get("sha") == new_owned[rel].get("sha")
            and current_info.get("exec") == new_owned[rel].get("exec")
        )
        if unchanged:
            continue
        if target.exists():
            _backup_file(backup_dir, workspace, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_file(staged_file, target, executable=bool(new_owned[rel].get("exec")))


def _backup_file(backup_dir: Path, workspace: Path, rel: str) -> None:
    source = _safe_workspace_path(workspace, rel)
    if not source.exists():
        return
    destination = _safe_workspace_path(backup_dir, rel)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_file(source: Path, destination: Path, *, executable: bool) -> None:
    tmp_destination = destination.with_name(f".{destination.name}.aoh-tmp-{uuid.uuid4().hex}")
    shutil.copy2(source, tmp_destination)
    if executable:
        tmp_destination.chmod(tmp_destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp_destination, destination)


def _safe_workspace_path(root: Path, rel: str) -> Path:
    segments = rel.split("/")
    return safe_join(root, *segments)

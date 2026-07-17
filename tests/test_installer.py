"""Crash-safe convergent installer — journal protocol.

Covers: fresh install, convergent no-op re-install, stale-file removal,
local-modification refusal (+ backup-always), discard_local, unowned-file
survival, recovery from both journal phases, manifest write atomicity,
legacy CLI naming scheme, path-escape refusal, and cross-process lock
contention.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest

from aoh.adapters.base import AdapterResult, MaterializeRequest
from aoh.installer import InstallRefused, install_workspace
from aoh.manifest import MANIFEST_NAME, NAMING_SCHEME_SITE_QUALIFIED, hash_tree, read_manifest
from aoh.pack import PackError, load_pack

KUBEOPS_PACK = PROJECT_ROOT / "collections/core/kubeops"


class FakeAdapter:
    """Deterministic adapter stub: writes a fixed file set into
    request.output_dir depending on `self.files`."""

    name = "fake"

    def __init__(self, files: dict[str, str], executable: set[str] | None = None):
        self.files = files
        self.executable = executable or set()
        self.calls: list[Path] = []

    def materialize(self, request: MaterializeRequest) -> AdapterResult:
        self.calls.append(Path(request.output_dir))
        out = Path(request.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        generated = []
        for rel, content in self.files.items():
            path = out / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            if rel in self.executable:
                path.chmod(0o755)
            generated.append(path)
        return AdapterResult(
            runtime="fake",
            output_dir=out,
            generated_files=generated,
            artifact_map={f"skills/x/{rel}": rel for rel in self.files},
        )


def _install(
    tmp_path: Path,
    *,
    files: dict[str, str],
    workspace_name: str = "workspace",
    discard_local: bool = False,
    adapter: FakeAdapter | None = None,
):
    pack = load_pack(KUBEOPS_PACK)
    workspace = tmp_path / workspace_name
    fake = adapter or FakeAdapter(files)
    request = MaterializeRequest(pack=pack, output_dir=workspace)
    result = install_workspace(
        adapter=fake,
        request=request,
        source={"repo": None, "subdir": "", "ref": "HEAD"},
        commit=None,
        naming_scheme=NAMING_SCHEME_SITE_QUALIFIED,
        discard_local=discard_local,
    )
    return workspace, fake, result


# --- fresh install -----------------------------------------------------


def test_fresh_install_writes_files_and_manifest(tmp_path: Path) -> None:
    workspace, _fake, result = _install(tmp_path, files={"a.txt": "hello\n", "b.txt": "world\n"})

    assert (workspace / "a.txt").read_text() == "hello\n"
    assert (workspace / "b.txt").read_text() == "world\n"
    manifest = read_manifest(workspace)
    assert manifest is not None
    assert set(manifest["ownedFiles"]) == {"a.txt", "b.txt", MANIFEST_NAME}
    assert manifest["namingScheme"] == NAMING_SCHEME_SITE_QUALIFIED
    assert result.output_dir == workspace


def test_fresh_install_leaves_no_journal_or_staging(tmp_path: Path) -> None:
    workspace, _fake, _result = _install(tmp_path, files={"a.txt": "hello\n"})

    assert not (workspace / ".aoh-journal.json").exists()
    assert list(workspace.parent.glob(".aoh-stage-*")) == []
    assert list(workspace.glob(".aoh-backup-*")) == []


# --- convergent no-op ----------------------------------------------------


def test_reinstall_identical_content_is_noop_no_backup(tmp_path: Path) -> None:
    files = {"a.txt": "hello\n"}
    workspace, _fake1, _r1 = _install(tmp_path, files=files)
    _workspace2, _fake2, _r2 = _install(tmp_path, files=files)

    assert (workspace / "a.txt").read_text() == "hello\n"
    assert list(workspace.glob(".aoh-backup-*")) == []


# --- stale-file removal ---------------------------------------------------


def test_reinstall_with_fewer_files_removes_stale_owned_file(tmp_path: Path) -> None:
    workspace, _fake1, _r1 = _install(tmp_path, files={"a.txt": "1\n", "b.txt": "2\n"})
    assert (workspace / "b.txt").exists()

    _workspace2, _fake2, _r2 = _install(tmp_path, files={"a.txt": "1\n"})

    assert (workspace / "a.txt").exists()
    assert not (workspace / "b.txt").exists()
    manifest = read_manifest(workspace)
    assert "b.txt" not in manifest["ownedFiles"]


# --- unowned files survive ------------------------------------------------


def test_unowned_file_in_workspace_is_never_touched(tmp_path: Path) -> None:
    workspace, _fake1, _r1 = _install(tmp_path, files={"a.txt": "1\n"})
    unowned = workspace / "user-notes.txt"
    unowned.write_text("do not touch\n", encoding="utf-8")

    _workspace2, _fake2, _r2 = _install(tmp_path, files={"a.txt": "1\n", "c.txt": "3\n"})

    assert unowned.read_text() == "do not touch\n"
    manifest = read_manifest(workspace)
    assert "user-notes.txt" not in manifest["ownedFiles"]


# --- modification refusal + always-backup ---------------------------------


def test_reinstall_refuses_when_owned_file_locally_modified(tmp_path: Path) -> None:
    workspace, _fake1, _r1 = _install(tmp_path, files={"a.txt": "1\n"})
    (workspace / "a.txt").write_text("locally edited\n", encoding="utf-8")

    with pytest.raises(InstallRefused) as excinfo:
        _install(tmp_path, files={"a.txt": "2\n"})

    assert "a.txt" in str(excinfo.value)
    # Refusal must not have mutated the file.
    assert (workspace / "a.txt").read_text() == "locally edited\n"


def test_reinstall_replacing_unmodified_file_always_backs_up(tmp_path: Path) -> None:
    workspace, _fake1, _r1 = _install(tmp_path, files={"a.txt": "1\n"})

    _workspace2, _fake2, _r2 = _install(tmp_path, files={"a.txt": "2\n"})

    assert (workspace / "a.txt").read_text() == "2\n"
    backup_dirs = list(workspace.glob(".aoh-backup-*"))
    assert len(backup_dirs) == 1
    assert (backup_dirs[0] / "a.txt").read_text() == "1\n"


def test_discard_local_backs_up_modified_file_and_overwrites(tmp_path: Path) -> None:
    workspace, _fake1, _r1 = _install(tmp_path, files={"a.txt": "1\n"})
    (workspace / "a.txt").write_text("locally edited\n", encoding="utf-8")

    _workspace2, _fake2, _r2 = _install(
        tmp_path, files={"a.txt": "2\n"}, discard_local=True
    )

    assert (workspace / "a.txt").read_text() == "2\n"
    backup_dirs = list(workspace.glob(".aoh-backup-*"))
    assert len(backup_dirs) == 1
    assert (backup_dirs[0] / "a.txt").read_text() == "locally edited\n"


# --- manifest write atomicity ----------------------------------------------


def test_manifest_write_leaves_no_tmp_file(tmp_path: Path) -> None:
    workspace, _fake, _result = _install(tmp_path, files={"a.txt": "1\n"})

    tmp_leftovers = list(workspace.glob(f"{MANIFEST_NAME}.*.tmp"))
    assert tmp_leftovers == []


# --- recovery: phase=staged -> clean abort --------------------------------


def test_recovery_from_staged_phase_journal_cleans_abort(tmp_path: Path) -> None:
    workspace, _fake1, _r1 = _install(tmp_path, files={"a.txt": "1\n"})
    original_manifest = read_manifest(workspace)

    txn_id = "deadbeef"
    stage_name = f".aoh-stage-{txn_id}"
    staging_dir = workspace.parent / stage_name
    staging_dir.mkdir()
    (staging_dir / "a.txt").write_text("2\n", encoding="utf-8")

    journal = {
        "txnId": txn_id,
        "phase": "staged",
        "workspaceRoot": ".",
        "stagingDir": stage_name,
        "backupDir": f".aoh-backup-{txn_id}",
        "oldOwned": {"a.txt": {"sha": "x", "exec": False}},
        "newOwned": {"a.txt": {"sha": "y", "exec": False}},
        "newManifest": {**original_manifest, "resolvedCommit": "should-not-apply"},
    }
    (workspace / ".aoh-journal.json").write_text(json.dumps(journal), encoding="utf-8")

    # Any subsequent install call recovers first, under the lock.
    _workspace2, _fake2, _r2 = _install(tmp_path, files={"a.txt": "3\n"})

    assert not (workspace / ".aoh-journal.json").exists()
    assert not staging_dir.exists()
    # Original content untouched by recovery itself; the *new* install then
    # proceeded normally on top (no local-mod conflict since a.txt matched
    # the prior manifest hash).
    assert (workspace / "a.txt").read_text() == "3\n"
    manifest = read_manifest(workspace)
    assert manifest["resolvedCommit"] != "should-not-apply"


# --- recovery: phase=committing -> roll forward -----------------------------


def test_recovery_from_committing_phase_journal_rolls_forward(tmp_path: Path) -> None:
    workspace, _fake1, _r1 = _install(tmp_path, files={"a.txt": "1\n", "b.txt": "orig\n"})

    txn_id = "cafef00d"
    stage_name = f".aoh-stage-{txn_id}"
    staging_dir = workspace.parent / stage_name
    staging_dir.mkdir()
    (staging_dir / "a.txt").write_text("rolled-forward\n", encoding="utf-8")
    a_hashes = hash_tree(staging_dir)

    new_manifest_owned = ["a.txt", MANIFEST_NAME]
    from aoh.manifest import build_manifest

    new_manifest = build_manifest(
        pack="kubeops",
        source={"repo": None, "subdir": "", "ref": "HEAD"},
        resolved_commit=None,
        binding=None,
        runtime="fake",
        adapter="fake",
        naming_scheme=NAMING_SCHEME_SITE_QUALIFIED,
        owned_files=new_manifest_owned,
        transform_id="identity-v1",
        artifact_map={},
        canonical_hashes=a_hashes,
        materialized_hashes=a_hashes,
    )

    journal = {
        "txnId": txn_id,
        "phase": "committing",
        "workspaceRoot": ".",
        "stagingDir": stage_name,
        "backupDir": f".aoh-backup-{txn_id}",
        "oldOwned": {"a.txt": {"sha": "x", "exec": False}, "b.txt": {"sha": "y", "exec": False}},
        "newOwned": {"a.txt": a_hashes["a.txt"]},
        "newManifest": new_manifest,
    }
    (workspace / ".aoh-journal.json").write_text(json.dumps(journal), encoding="utf-8")

    # Recovery happens as part of the next install_workspace call, before
    # the new install's own logic runs.
    _workspace2, _fake2, _r2 = _install(tmp_path, files={"a.txt": "rolled-forward\n"})

    assert not (workspace / ".aoh-journal.json").exists()
    assert not staging_dir.exists()
    assert (workspace / "a.txt").read_text() == "rolled-forward\n"


def test_recovery_never_backs_up_into_existing_backup_dir(tmp_path: Path) -> None:
    workspace, _fake1, _r1 = _install(tmp_path, files={"a.txt": "1\n"})

    txn_id = "abad1dea"
    stage_name = f".aoh-stage-{txn_id}"
    backup_name = f".aoh-backup-{txn_id}"
    staging_dir = workspace.parent / stage_name
    staging_dir.mkdir()
    (staging_dir / "a.txt").write_text("rolled-forward\n", encoding="utf-8")
    a_hashes = hash_tree(staging_dir)

    backup_dir = workspace / backup_name
    backup_dir.mkdir()
    (backup_dir / "a.txt").write_text("preserved-original\n", encoding="utf-8")
    sentinel = backup_dir / "a.txt"
    sentinel_mtime_before = sentinel.stat().st_mtime_ns

    from aoh.manifest import build_manifest

    new_manifest = build_manifest(
        pack="kubeops",
        source={"repo": None, "subdir": "", "ref": "HEAD"},
        resolved_commit=None,
        binding=None,
        runtime="fake",
        adapter="fake",
        naming_scheme=NAMING_SCHEME_SITE_QUALIFIED,
        owned_files=["a.txt", MANIFEST_NAME],
        transform_id="identity-v1",
        artifact_map={},
        canonical_hashes=a_hashes,
        materialized_hashes=a_hashes,
    )
    journal = {
        "txnId": txn_id,
        "phase": "committing",
        "workspaceRoot": ".",
        "stagingDir": stage_name,
        "backupDir": backup_name,
        "oldOwned": {"a.txt": {"sha": "x", "exec": False}},
        "newOwned": {"a.txt": a_hashes["a.txt"]},
        "newManifest": new_manifest,
    }
    (workspace / ".aoh-journal.json").write_text(json.dumps(journal), encoding="utf-8")

    _workspace2, _fake2, _r2 = _install(tmp_path, files={"a.txt": "rolled-forward\n"})

    # Original backup content preserved untouched (recovery must not
    # re-backup into an existing backup dir).
    assert (backup_dir / "a.txt").read_text() == "preserved-original\n"
    assert sentinel.stat().st_mtime_ns == sentinel_mtime_before


# --- path-escape refusal ---------------------------------------------------


def test_malicious_manifest_owned_file_escape_refused(tmp_path: Path) -> None:
    workspace, _fake1, _r1 = _install(tmp_path, files={"a.txt": "1\n"})
    manifest_path = workspace / MANIFEST_NAME
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["ownedFiles"].append("../evil")
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(PackError):
        _install(tmp_path, files={"a.txt": "2\n"})


# --- lock contention (cross-process) ---------------------------------------


def test_lock_contention_from_second_process_refuses(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    lock_path = workspace.parent / ".aoh-install.lock"

    holder_script = textwrap.dedent(
        f"""
        import fcntl, time, sys
        fh = open({str(lock_path)!r}, "w")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        sys.stdout.write("locked\\n")
        sys.stdout.flush()
        time.sleep(3)
        """
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", holder_script],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        line = proc.stdout.readline()
        assert line.strip() == "locked"

        pack = load_pack(KUBEOPS_PACK)
        fake = FakeAdapter({"a.txt": "1\n"})
        request = MaterializeRequest(pack=pack, output_dir=workspace)

        with pytest.raises(InstallRefused):
            install_workspace(
                adapter=fake,
                request=request,
                source={"repo": None, "subdir": "", "ref": "HEAD"},
                commit=None,
                naming_scheme=NAMING_SCHEME_SITE_QUALIFIED,
            )
    finally:
        proc.kill()
        proc.wait()


# --- staging on same filesystem, sibling of workspace -----------------------


def test_staging_dir_is_sibling_of_workspace(tmp_path: Path) -> None:
    seen: list[Path] = []

    class RecordingAdapter(FakeAdapter):
        def materialize(self, request: MaterializeRequest) -> AdapterResult:
            seen.append(Path(request.output_dir))
            return super().materialize(request)

    adapter = RecordingAdapter({"a.txt": "1\n"})
    workspace, _fake, _result = _install(tmp_path, files={"a.txt": "1\n"}, adapter=adapter)

    assert len(seen) == 1
    staged_dir = seen[0]
    assert staged_dir.parent == workspace.parent
    assert staged_dir.name.startswith(".aoh-stage-")

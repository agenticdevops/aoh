"""SiteLock — minimal Phase A lock (F1 subset): resolves site pack refs to
commits and pins fan-out installs to them.

Covers: load/write round trip, missing-file => None, camelCase keys,
apiVersion/kind strict, local-source entries recorded uniformly ({local:
true, path}), malformed lock document rejected.
"""

from __future__ import annotations

from pathlib import Path
import sys
import textwrap

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.pack import PackError
from aoh.site import LockedPack, SiteLock, load_site_lock, write_site_lock


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# load_site_lock — missing file
# ---------------------------------------------------------------------------


def test_load_site_lock_missing_file_returns_none(tmp_path: Path) -> None:
    assert load_site_lock(tmp_path) is None


# ---------------------------------------------------------------------------
# load_site_lock — happy path
# ---------------------------------------------------------------------------


def test_load_site_lock_reads_git_pack_entry(tmp_path: Path) -> None:
    write(
        tmp_path / "site.lock.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: SiteLock
        packs:
          kubeops:
            repo: https://github.com/agenticdevops/aoh
            subdir: collections/core/kubeops
            requestedRef: main
            resolvedCommit: deadbeefdeadbeefdeadbeefdeadbeefdeadbeef
        """,
    )

    lock = load_site_lock(tmp_path)

    assert lock is not None
    assert isinstance(lock, SiteLock)
    assert "kubeops" in lock.packs
    entry = lock.packs["kubeops"]
    assert isinstance(entry, LockedPack)
    assert entry.repo == "https://github.com/agenticdevops/aoh"
    assert entry.subdir == "collections/core/kubeops"
    assert entry.requested_ref == "main"
    assert entry.resolved_commit == "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    assert entry.local is False


def test_load_site_lock_reads_local_pack_entry(tmp_path: Path) -> None:
    write(
        tmp_path / "site.lock.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: SiteLock
        packs:
          kubeops:
            local: true
            path: /abs/local/kubeops
        """,
    )

    lock = load_site_lock(tmp_path)

    assert lock is not None
    entry = lock.packs["kubeops"]
    assert entry.local is True
    assert entry.local_path == Path("/abs/local/kubeops")
    assert entry.resolved_commit is None


def test_load_site_lock_empty_packs_ok(tmp_path: Path) -> None:
    write(
        tmp_path / "site.lock.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: SiteLock
        packs: {}
        """,
    )

    lock = load_site_lock(tmp_path)
    assert lock is not None
    assert lock.packs == {}


# ---------------------------------------------------------------------------
# load_site_lock — strict apiVersion/kind
# ---------------------------------------------------------------------------


def test_load_site_lock_rejects_wrong_kind(tmp_path: Path) -> None:
    write(
        tmp_path / "site.lock.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: NotASiteLock
        packs: {}
        """,
    )

    with pytest.raises(PackError):
        load_site_lock(tmp_path)


def test_load_site_lock_rejects_wrong_api_version(tmp_path: Path) -> None:
    write(
        tmp_path / "site.lock.yaml",
        """
        apiVersion: openagentix.io/v1alpha1
        kind: SiteLock
        packs: {}
        """,
    )

    with pytest.raises(PackError):
        load_site_lock(tmp_path)


# ---------------------------------------------------------------------------
# write_site_lock — round trip + camelCase
# ---------------------------------------------------------------------------


def test_write_site_lock_round_trips(tmp_path: Path) -> None:
    lock = SiteLock(
        root=tmp_path,
        packs={
            "kubeops": LockedPack(
                repo="https://github.com/agenticdevops/aoh",
                subdir="collections/core/kubeops",
                requested_ref="main",
                resolved_commit="a" * 40,
                local=False,
                local_path=None,
            ),
            "localpack": LockedPack(
                repo=None,
                subdir="",
                requested_ref="HEAD",
                resolved_commit=None,
                local=True,
                local_path=Path("/abs/local/pack"),
            ),
        },
    )

    path = write_site_lock(tmp_path, lock)

    assert path == tmp_path / "site.lock.yaml"

    reloaded = load_site_lock(tmp_path)
    assert reloaded is not None
    assert reloaded.packs["kubeops"].resolved_commit == "a" * 40
    assert reloaded.packs["localpack"].local is True
    assert reloaded.packs["localpack"].local_path == Path("/abs/local/pack")


def test_write_site_lock_uses_camel_case_keys_on_disk(tmp_path: Path) -> None:
    lock = SiteLock(
        root=tmp_path,
        packs={
            "kubeops": LockedPack(
                repo="https://x",
                subdir="kubeops",
                requested_ref="main",
                resolved_commit="a" * 40,
                local=False,
                local_path=None,
            ),
        },
    )
    write_site_lock(tmp_path, lock)

    raw = (tmp_path / "site.lock.yaml").read_text(encoding="utf-8")
    assert "requestedRef" in raw
    assert "resolvedCommit" in raw
    assert "requested_ref" not in raw
    assert "resolved_commit" not in raw

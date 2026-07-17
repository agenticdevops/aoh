"""aoh-manifest.json: build/read/write, atomicity, and path-safety validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest

from aoh.manifest import (
    MANIFEST_NAME,
    NAMING_SCHEME_LEGACY,
    NAMING_SCHEME_SITE_QUALIFIED,
    build_manifest,
    hash_tree,
    read_manifest,
    write_manifest,
)
from aoh.pack import PackError


def _sample_manifest_doc(workspace: Path) -> dict:
    (workspace / "SKILL.md").write_text("hello\n", encoding="utf-8")
    hashes = hash_tree(workspace)
    return build_manifest(
        pack="kubeops",
        source={"repo": "https://example.com/repo.git", "subdir": "", "ref": "main"},
        resolved_commit="abc123",
        binding="kubeops-sresquad",
        runtime="claude-code",
        adapter="claude-code",
        naming_scheme=NAMING_SCHEME_SITE_QUALIFIED,
        owned_files=["SKILL.md"],
        transform_id="identity-v1",
        artifact_map={"skills/x/SKILL.md": "SKILL.md"},
        canonical_hashes=hashes,
        materialized_hashes=hashes,
    )


def test_hash_tree_reports_sha_and_exec_per_file(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hi\n", encoding="utf-8")
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    script.chmod(0o755)

    hashes = hash_tree(tmp_path)

    assert set(hashes) == {"a.txt", "run.sh"}
    assert hashes["a.txt"]["exec"] is False
    assert hashes["run.sh"]["exec"] is True
    assert len(hashes["a.txt"]["sha"]) == 64  # sha256 hex


def test_build_manifest_has_expected_fields(tmp_path: Path) -> None:
    doc = _sample_manifest_doc(tmp_path)

    assert doc["pack"] == "kubeops"
    assert doc["source"] == {"repo": "https://example.com/repo.git", "subdir": "", "ref": "main"}
    assert doc["resolvedCommit"] == "abc123"
    assert doc["binding"] == "kubeops-sresquad"
    assert doc["runtime"] == "claude-code"
    assert doc["adapter"] == "claude-code"
    assert doc["namingScheme"] == NAMING_SCHEME_SITE_QUALIFIED
    assert doc["ownedFiles"] == ["SKILL.md"]
    assert doc["transformId"] == "identity-v1"
    assert doc["artifactMap"] == {"skills/x/SKILL.md": "SKILL.md"}
    assert "canonicalHashes" in doc and "materializedHashes" in doc
    assert "generatedAt" in doc and doc["generatedAt"].endswith("Z") or "+" in doc["generatedAt"]
    assert "txn" not in doc


def test_write_manifest_is_atomic_no_tmp_file_left(tmp_path: Path) -> None:
    doc = _sample_manifest_doc(tmp_path)

    write_manifest(tmp_path, doc)

    manifest_path = tmp_path / MANIFEST_NAME
    assert manifest_path.exists()
    tmp_files = list(tmp_path.glob(f"{MANIFEST_NAME}.*.tmp"))
    assert tmp_files == []
    on_disk = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert on_disk["pack"] == "kubeops"


def test_read_manifest_returns_none_when_absent(tmp_path: Path) -> None:
    assert read_manifest(tmp_path) is None


def test_read_manifest_round_trips(tmp_path: Path) -> None:
    doc = _sample_manifest_doc(tmp_path)
    write_manifest(tmp_path, doc)

    read_back = read_manifest(tmp_path)

    assert read_back == doc


def test_read_manifest_rejects_escaping_owned_file(tmp_path: Path) -> None:
    doc = _sample_manifest_doc(tmp_path)
    doc["ownedFiles"] = ["../evil"]
    write_manifest(tmp_path, doc)

    with pytest.raises(PackError):
        read_manifest(tmp_path)


def test_read_manifest_rejects_escaping_artifact_map_value(tmp_path: Path) -> None:
    doc = _sample_manifest_doc(tmp_path)
    doc["artifactMap"] = {"skills/x/SKILL.md": "../../evil"}
    write_manifest(tmp_path, doc)

    with pytest.raises(PackError):
        read_manifest(tmp_path)


def test_read_manifest_rejects_absolute_owned_file(tmp_path: Path) -> None:
    doc = _sample_manifest_doc(tmp_path)
    doc["ownedFiles"] = ["/etc/passwd"]
    write_manifest(tmp_path, doc)

    with pytest.raises(PackError):
        read_manifest(tmp_path)


def test_naming_scheme_constants() -> None:
    assert NAMING_SCHEME_SITE_QUALIFIED == "v2-site-qualified"
    assert NAMING_SCHEME_LEGACY == "v1-legacy"

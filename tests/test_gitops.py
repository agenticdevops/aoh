from __future__ import annotations

import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.gitops import (
    GitOpsError,
    ensure_mirror,
    export_tree,
    mirror_path,
    resolve_commit,
    source_checkout,
)
from aoh.site import PackSource


# ---------------------------------------------------------------------------
# fixture helpers
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


def _seed_minimal_pack(work: Path, pack_dir: str = "collections/demo") -> None:
    root = work / pack_dir
    write(
        root / "AOH.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Pack
        metadata:
          name: demo
          displayName: Demo
          description: Minimal demo pack for gitops tests.
          owner: Test
        """,
    )
    write(
        root / "skills" / "demo-skill" / "SKILL.md",
        """
        ---
        name: demo-skill
        description: Use when demoing gitops export behavior.
        ---

        # Demo Skill

        This is a minimal skill body for gitops tests.
        """,
    )


def make_bare_repo(tmp_path: Path, name: str = "origin.git", pack_dir: str = "collections/demo") -> Path:
    """Create a bare repo seeded (via a temp work clone) with a minimal valid
    v1alpha2 pack under `pack_dir`, committed and tagged `v1`. Returns the
    bare repo path (a `file://` URL usable as a git remote)."""
    bare = tmp_path / name
    _run(["git", "init", "--bare", "-q", str(bare)], cwd=tmp_path)

    work = tmp_path / f"_seed-{name}"
    _run(["git", "init", "-q", str(work)], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "Test"], cwd=work)

    _seed_minimal_pack(work, pack_dir)

    _run(["git", "add", "-A"], cwd=work)
    _run(["git", "commit", "-q", "-m", "seed"], cwd=work)
    _run(["git", "tag", "v1"], cwd=work)
    _run(["git", "remote", "add", "origin", str(bare)], cwd=work)
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)
    _run(["git", "push", "-q", "origin", "v1"], cwd=work)

    return bare


def bare_repo_url(bare: Path) -> str:
    return f"file://{bare}"


def commit_extra(bare: Path, tmp_path: Path, filename: str = "extra.txt", tag: str | None = None) -> str:
    """Clone the bare repo, add a new file, commit, push, return new commit sha."""
    work = tmp_path / f"_extra-{filename.replace('/', '_')}"
    _run(["git", "clone", "-q", str(bare), str(work)], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "Test"], cwd=work)
    write(work / filename, "extra content")
    _run(["git", "add", "-A"], cwd=work)
    _run(["git", "commit", "-q", "-m", "extra"], cwd=work)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=work).stdout.strip()
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)
    if tag:
        _run(["git", "tag", "-f", tag], cwd=work)
        _run(["git", "push", "-q", "-f", "origin", tag], cwd=work)
    return sha


def add_submodule_entry(bare: Path, tmp_path: Path, sub_path: str = "collections/demo/evil-sub") -> str:
    """Fake a submodule (gitlink, mode 160000) entry via update-index and
    commit it, without an actual .gitmodules or nested repo. Returns the new
    commit sha."""
    work = tmp_path / "_submod"
    _run(["git", "clone", "-q", str(bare), str(work)], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "Test"], cwd=work)
    fake_sha = "a" * 40
    _run(
        ["git", "update-index", "--add", "--cacheinfo", f"160000,{fake_sha},{sub_path}"],
        cwd=work,
    )
    _run(["git", "commit", "-q", "-m", "add fake submodule"], cwd=work)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=work).stdout.strip()
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)
    return sha


def add_symlink_entry(bare: Path, tmp_path: Path, link_path: str = "collections/demo/evil-link") -> str:
    """Commit a real symlink inside the pack tree. Returns the new commit sha."""
    work = tmp_path / "_symlink"
    _run(["git", "clone", "-q", str(bare), str(work)], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "Test"], cwd=work)
    target = work / link_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to("/etc/passwd")
    _run(["git", "add", "-A"], cwd=work)
    _run(["git", "commit", "-q", "-m", "add symlink"], cwd=work)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=work).stdout.strip()
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)
    return sha


# ---------------------------------------------------------------------------
# mirror_path
# ---------------------------------------------------------------------------


def test_mirror_path_is_deterministic_sha256_prefix(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    p1 = mirror_path(cache_dir, "https://example.com/foo.git")
    p2 = mirror_path(cache_dir, "https://example.com/foo.git")
    assert p1 == p2
    assert p1.parent == cache_dir
    assert p1.suffix == ".git"
    assert len(p1.stem) == 16


def test_mirror_path_differs_by_url(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    p1 = mirror_path(cache_dir, "https://example.com/foo.git")
    p2 = mirror_path(cache_dir, "https://example.com/bar.git")
    assert p1 != p2


def test_mirror_path_normalizes_trivial_url_variants(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    p1 = mirror_path(cache_dir, "https://example.com/foo.git")
    p2 = mirror_path(cache_dir, "https://example.com/foo.git/")
    assert p1 == p2


# ---------------------------------------------------------------------------
# ensure_mirror
# ---------------------------------------------------------------------------


def test_ensure_mirror_clones_bare_mirror(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"

    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))

    assert mirror.exists()
    assert mirror == mirror_path(cache_dir, bare_repo_url(bare))
    # bare mirror clone: HEAD file must exist
    assert (mirror / "HEAD").exists()


def test_ensure_mirror_second_call_updates_existing_mirror(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"

    mirror1 = ensure_mirror(cache_dir, bare_repo_url(bare))
    new_sha = commit_extra(bare, tmp_path)
    mirror2 = ensure_mirror(cache_dir, bare_repo_url(bare))

    assert mirror1 == mirror2
    resolved = resolve_commit(mirror2, "main")
    assert resolved == new_sha


def test_ensure_mirror_prunes_removed_refs(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    commit_extra(bare, tmp_path, tag="transient")

    ensure_mirror(cache_dir, bare_repo_url(bare))

    _run(["git", "tag", "-d", "transient"], cwd=bare)

    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))

    result = subprocess.run(
        ["git", "rev-parse", "transient"],
        cwd=mirror,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_ensure_mirror_releases_lock_after_call(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"

    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))
    lock_path = mirror.parent / (mirror.name + ".lock")

    assert lock_path.exists()

    # lock must be free again: another process should be able to acquire it
    # immediately (non-blocking)
    script = f"""
import fcntl
with open({str(lock_path)!r}, "w") as fh:
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    print("ACQUIRED")
"""
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert "ACQUIRED" in proc.stdout, proc.stderr


def test_ensure_mirror_cross_process_contention(tmp_path: Path) -> None:
    """A second OS process holding the mirror lock must block/serialize the
    main process's ensure_mirror call — the update must not run concurrently
    with an in-progress clone."""
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"

    # Pre-create the mirror so the lock path exists in a known location.
    ensure_mirror(cache_dir, bare_repo_url(bare))
    mirror = mirror_path(cache_dir, bare_repo_url(bare))
    lock_path = mirror.parent / (mirror.name + ".lock")

    hold_script = f"""
import fcntl, time
with open({str(lock_path)!r}, "w") as fh:
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    print("HELD", flush=True)
    time.sleep(1.5)
"""
    holder = subprocess.Popen(
        [sys.executable, "-c", hold_script],
        stdout=subprocess.PIPE,
        text=True,
    )
    # wait for the holder to actually acquire the lock
    line = holder.stdout.readline()
    assert "HELD" in line

    start = time.monotonic()
    mirror2 = ensure_mirror(cache_dir, bare_repo_url(bare))
    elapsed = time.monotonic() - start

    holder.wait(timeout=5)

    assert mirror2 == mirror
    # ensure_mirror had to wait for the holder to release (~1.5s sleep)
    assert elapsed >= 1.0


# ---------------------------------------------------------------------------
# resolve_commit
# ---------------------------------------------------------------------------


def test_resolve_commit_tag(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))

    sha = resolve_commit(mirror, "v1")

    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


def test_resolve_commit_head_alias(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))

    sha_head = resolve_commit(mirror, "HEAD")
    sha_tag = resolve_commit(mirror, "v1")

    assert sha_head == sha_tag


def test_resolve_commit_unknown_ref_raises(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))

    with pytest.raises(GitOpsError):
        resolve_commit(mirror, "does-not-exist")


# ---------------------------------------------------------------------------
# export_tree
# ---------------------------------------------------------------------------


def test_export_tree_full_repo(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))
    commit = resolve_commit(mirror, "v1")
    dest = tmp_path / "exported"

    export_tree(mirror, commit, "", dest)

    assert (dest / "collections" / "demo" / "AOH.yaml").exists()
    assert (dest / "collections" / "demo" / "skills" / "demo-skill" / "SKILL.md").exists()


def test_export_tree_subdir_only(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))
    commit = resolve_commit(mirror, "v1")
    dest = tmp_path / "exported"

    export_tree(mirror, commit, "collections/demo", dest)

    assert (dest / "AOH.yaml").exists()
    assert (dest / "skills" / "demo-skill" / "SKILL.md").exists()
    assert not (dest / "collections").exists()


def test_export_tree_rejects_submodule_entry_before_extraction(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))
    add_submodule_entry(bare, tmp_path)
    ensure_mirror(cache_dir, bare_repo_url(bare))
    commit = resolve_commit(mirror, "main")
    dest = tmp_path / "exported-submodule"

    with pytest.raises(GitOpsError):
        export_tree(mirror, commit, "", dest)

    assert not dest.exists()


def test_export_tree_rejects_symlink_entry_before_extraction(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))
    add_symlink_entry(bare, tmp_path)
    ensure_mirror(cache_dir, bare_repo_url(bare))
    commit = resolve_commit(mirror, "main")
    dest = tmp_path / "exported-symlink"

    with pytest.raises(GitOpsError):
        export_tree(mirror, commit, "", dest)

    # PREFLIGHT must reject before ANY extraction: no partial dest left behind
    assert not dest.exists()


def test_export_tree_rejects_symlink_in_subdir(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))
    add_symlink_entry(bare, tmp_path, link_path="collections/demo/skills/evil-link")
    ensure_mirror(cache_dir, bare_repo_url(bare))
    commit = resolve_commit(mirror, "main")
    dest = tmp_path / "exported-symlink-subdir"

    with pytest.raises(GitOpsError):
        export_tree(mirror, commit, "collections/demo", dest)

    assert not dest.exists()


def test_export_tree_unknown_subdir_raises(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))
    commit = resolve_commit(mirror, "v1")
    dest = tmp_path / "exported-missing"

    with pytest.raises(GitOpsError):
        export_tree(mirror, commit, "does/not/exist", dest)

    assert not dest.exists()


def test_export_tree_result_has_no_symlinks_or_gitlinks(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    cache_dir = tmp_path / "cache"
    mirror = ensure_mirror(cache_dir, bare_repo_url(bare))
    commit = resolve_commit(mirror, "v1")
    dest = tmp_path / "exported-clean"

    export_tree(mirror, commit, "", dest)

    for path in dest.rglob("*"):
        assert not path.is_symlink(), f"{path} must not be a symlink"


# ---------------------------------------------------------------------------
# source_checkout — local
# ---------------------------------------------------------------------------


def test_source_checkout_local_returns_path_and_local_marker(tmp_path: Path) -> None:
    local_pack = tmp_path / "local-pack"
    _seed_minimal_pack(tmp_path, pack_dir="local-pack")
    source = PackSource(repo=None, subdir="", ref="HEAD", local_path=local_pack)
    cache_dir = tmp_path / "cache"

    path, origin = source_checkout(source, cache_dir)

    assert path == local_pack
    assert origin == "local"


def test_source_checkout_local_rejects_symlink_inside_tree(tmp_path: Path) -> None:
    local_pack = tmp_path / "local-pack-evil"
    _seed_minimal_pack(tmp_path, pack_dir="local-pack-evil")
    outside_target = tmp_path / "outside-secret"
    outside_target.write_text("secret", encoding="utf-8")
    (local_pack / "skills" / "evil-link").symlink_to(outside_target)

    source = PackSource(repo=None, subdir="", ref="HEAD", local_path=local_pack)
    cache_dir = tmp_path / "cache"

    with pytest.raises((GitOpsError,) + (Exception,)) as excinfo:
        source_checkout(source, cache_dir)
    # must specifically be a refusal-style error (GitOpsError or PackError,
    # both are ValueError subclasses) — nothing materialized as a result
    assert isinstance(excinfo.value, ValueError)


def test_source_checkout_local_symlink_refusal_is_precise(tmp_path: Path) -> None:
    from aoh.pack import PackError

    local_pack = tmp_path / "local-pack-evil2"
    _seed_minimal_pack(tmp_path, pack_dir="local-pack-evil2")
    outside_target = tmp_path / "outside-secret2"
    outside_target.write_text("secret", encoding="utf-8")
    (local_pack / "evil-link").symlink_to(outside_target)

    source = PackSource(repo=None, subdir="", ref="HEAD", local_path=local_pack)
    cache_dir = tmp_path / "cache"

    with pytest.raises((GitOpsError, PackError)):
        source_checkout(source, cache_dir)


# ---------------------------------------------------------------------------
# source_checkout — git
# ---------------------------------------------------------------------------


def test_source_checkout_git_exports_and_returns_git_marker(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    source = PackSource(repo=bare_repo_url(bare), subdir="collections/demo", ref="v1", local_path=None)
    cache_dir = tmp_path / "cache"

    path, origin = source_checkout(source, cache_dir)

    assert origin == "git"
    assert path.exists()
    assert (path / "AOH.yaml").exists()
    assert (path / "skills" / "demo-skill" / "SKILL.md").exists()
    assert path.is_relative_to(cache_dir / "exports")


def test_source_checkout_git_export_path_includes_format_version_key(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    source = PackSource(repo=bare_repo_url(bare), subdir="collections/demo", ref="v1", local_path=None)
    cache_dir = tmp_path / "cache"

    path, _ = source_checkout(source, cache_dir)

    assert "-v1" in path.name or path.name.endswith("-v1")


def test_source_checkout_git_writes_completion_marker(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    source = PackSource(repo=bare_repo_url(bare), subdir="collections/demo", ref="v1", local_path=None)
    cache_dir = tmp_path / "cache"

    path, _ = source_checkout(source, cache_dir)

    assert (path / ".complete").exists()


def test_source_checkout_git_reuses_existing_complete_export(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    source = PackSource(repo=bare_repo_url(bare), subdir="collections/demo", ref="v1", local_path=None)
    cache_dir = tmp_path / "cache"

    path1, _ = source_checkout(source, cache_dir)
    sentinel = path1 / "sentinel-not-touched.txt"
    sentinel.write_text("keep me", encoding="utf-8")

    path2, _ = source_checkout(source, cache_dir)

    assert path1 == path2
    # reused, not wiped/re-exported
    assert sentinel.exists()


def test_source_checkout_git_marker_less_dir_is_wiped_and_reexported(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    source = PackSource(repo=bare_repo_url(bare), subdir="collections/demo", ref="v1", local_path=None)
    cache_dir = tmp_path / "cache"

    path1, _ = source_checkout(source, cache_dir)
    # simulate a crash mid-export: remove the marker, leave stray content
    (path1 / ".complete").unlink()
    stray = path1 / "stray-partial-file.txt"
    stray.write_text("partial junk", encoding="utf-8")

    path2, _ = source_checkout(source, cache_dir)

    assert path1 == path2
    assert (path2 / ".complete").exists()
    assert not stray.exists()
    assert (path2 / "AOH.yaml").exists()


def test_source_checkout_git_different_commit_different_export_dir(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    source_v1 = PackSource(repo=bare_repo_url(bare), subdir="collections/demo", ref="v1", local_path=None)
    cache_dir = tmp_path / "cache"

    path1, _ = source_checkout(source_v1, cache_dir)

    commit_extra(bare, tmp_path, filename="collections/demo/skills/demo-skill/extra.txt")
    source_main = PackSource(repo=bare_repo_url(bare), subdir="collections/demo", ref="main", local_path=None)
    path2, _ = source_checkout(source_main, cache_dir)

    assert path1 != path2
    assert (path2 / "skills" / "demo-skill" / "extra.txt").exists()
    assert not (path1 / "skills" / "demo-skill" / "extra.txt").exists()


def test_source_checkout_git_rejects_submodule(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    add_submodule_entry(bare, tmp_path)
    source = PackSource(repo=bare_repo_url(bare), subdir="collections/demo", ref="main", local_path=None)
    cache_dir = tmp_path / "cache"

    with pytest.raises(GitOpsError):
        source_checkout(source, cache_dir)

    exports_dir = cache_dir / "exports"
    if exports_dir.exists():
        for entry in exports_dir.iterdir():
            assert not (entry / ".complete").exists()


def test_source_checkout_git_rejects_symlink(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    add_symlink_entry(bare, tmp_path, link_path="collections/demo/evil-link")
    source = PackSource(repo=bare_repo_url(bare), subdir="collections/demo", ref="main", local_path=None)
    cache_dir = tmp_path / "cache"

    with pytest.raises(GitOpsError):
        source_checkout(source, cache_dir)

    exports_dir = cache_dir / "exports"
    if exports_dir.exists():
        for entry in exports_dir.iterdir():
            assert not (entry / ".complete").exists()

from __future__ import annotations

import fcntl
import hashlib
import os
import shutil
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from aoh.site import PackSource

EXPORT_FORMAT = "v1"

# git ls-tree object modes that must never be extracted.
_MODE_SYMLINK = "120000"
_MODE_GITLINK = "160000"  # submodule


class GitOpsError(ValueError):
    """Raised when a git operation fails or an unsafe tree entry is found."""


# ---------------------------------------------------------------------------
# locking
# ---------------------------------------------------------------------------


@contextmanager
def _locked(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive lock on the adjacent `.lock` file for the whole
    critical section. The fd is held open for the duration and released
    (unlocked + closed) in `finally`."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


# ---------------------------------------------------------------------------
# subprocess helper
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise GitOpsError(f"git {' '.join(args)} failed: {stderr}") from None
    except FileNotFoundError as exc:
        raise GitOpsError(f"git executable not found: {exc}") from None
    return result.stdout


# ---------------------------------------------------------------------------
# mirror cache
# ---------------------------------------------------------------------------


def _normalize_url(url: str) -> str:
    return url.rstrip("/")


def mirror_path(cache_dir: Path, url: str) -> Path:
    """Deterministic bare-mirror location for `url` under `cache_dir`."""
    digest = hashlib.sha256(_normalize_url(url).encode("utf-8")).hexdigest()[:16]
    return Path(cache_dir) / f"{digest}.git"


def ensure_mirror(cache_dir: Path, url: str) -> Path:
    """Ensure a bare mirror of `url` exists and is up to date under
    `cache_dir`, serialized by an adjacent `.lock` file (fcntl LOCK_EX, held
    for the whole critical section, released in `finally`)."""
    mirror = mirror_path(cache_dir, url)
    lock_path = mirror.parent / (mirror.name + ".lock")

    with _locked(lock_path):
        if mirror.exists():
            _git(["remote", "update", "--prune"], cwd=mirror)
        else:
            mirror.parent.mkdir(parents=True, exist_ok=True)
            tmp_dir = Path(tempfile.mkdtemp(prefix=".clone-", dir=str(mirror.parent)))
            try:
                _git(["clone", "--mirror", url, str(tmp_dir)])
                tmp_dir.rename(mirror)
            except BaseException:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                raise

    return mirror


def resolve_commit(mirror: Path, ref: str) -> str:
    """Resolve `ref` to a full commit sha in `mirror`."""
    out = _git(["rev-parse", f"{ref}^{{commit}}"], cwd=mirror)
    return out.strip()


# ---------------------------------------------------------------------------
# safe export
# ---------------------------------------------------------------------------


def _preflight_tree(mirror: Path, commit: str, subdir: str) -> list[tuple[str, str, str]]:
    """Return parsed `git ls-tree -r` entries as (mode, sha, path) tuples,
    scoped to `subdir` if given. Raises GitOpsError if any entry is a
    symlink (120000) or submodule/gitlink (160000), BEFORE any extraction.
    """
    args = ["ls-tree", "-r", commit]
    if subdir:
        args.append(subdir)
    output = _git(args, cwd=mirror)

    lines = [line for line in output.splitlines() if line.strip()]
    if subdir and not lines:
        raise GitOpsError(f"path `{subdir}` not found at commit {commit}")

    entries: list[tuple[str, str, str]] = []
    for line in lines:
        # format: "<mode> <type> <sha>\t<path>"
        meta, path = line.split("\t", 1)
        mode, _obj_type, sha = meta.split(" ", 2)
        if mode == _MODE_SYMLINK:
            raise GitOpsError(f"refusing export: symlink entry `{path}` at commit {commit}")
        if mode == _MODE_GITLINK:
            raise GitOpsError(f"refusing export: submodule entry `{path}` at commit {commit}")
        entries.append((mode, sha, path))
    return entries


def export_tree(mirror: Path, commit: str, subdir: str, dest: Path) -> None:
    """Export the tree at `commit` (optionally scoped to `subdir`) from
    `mirror` into `dest`.

    PREFLIGHT: `git ls-tree -r` is checked for symlink/submodule entries
    BEFORE any extraction happens. Extraction goes into a private temp
    directory (never `dest` directly), extracted paths are verified to stay
    contained, then the temp directory is atomically renamed onto `dest`.
    """
    dest = Path(dest)
    _preflight_tree(mirror, commit, subdir)

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix=".export-", dir=str(dest.parent)))
    try:
        raw_dir = tmp_dir / "raw"
        raw_dir.mkdir()

        # `git archive <commit> <subdir>` keeps the subdir prefix in the
        # resulting tar (it does not strip it), so extract into a private
        # `raw/` dir and then locate the subdir tree within it.
        archive_args = ["archive", commit]
        if subdir:
            archive_args.append(subdir)
        proc_archive = subprocess.Popen(
            ["git", *archive_args],
            cwd=mirror,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc_tar = subprocess.Popen(
            ["tar", "-x", "-C", str(raw_dir)],
            stdin=proc_archive.stdout,
            stderr=subprocess.PIPE,
        )
        assert proc_archive.stdout is not None
        proc_archive.stdout.close()
        _, tar_stderr = proc_tar.communicate()
        _, archive_stderr = proc_archive.communicate()

        if proc_archive.returncode != 0:
            raise GitOpsError(
                f"git archive failed: {(archive_stderr or b'').decode(errors='replace').strip()}"
            )
        if proc_tar.returncode != 0:
            raise GitOpsError(f"tar extraction failed: {(tar_stderr or b'').decode(errors='replace').strip()}")

        _verify_containment(raw_dir)

        content_root = raw_dir
        if subdir:
            for part in subdir.split("/"):
                content_root = content_root / part

        if not content_root.exists() or not content_root.is_dir():
            raise GitOpsError(f"exported subdir `{subdir}` not found after extraction")

        if dest.exists():
            shutil.rmtree(dest)
        content_root.rename(dest)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _verify_containment(root: Path) -> None:
    resolved_root = root.resolve()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise GitOpsError(f"extracted path `{path}` is a symlink — refusing")
        try:
            path.resolve().relative_to(resolved_root)
        except ValueError:
            raise GitOpsError(f"extracted path `{path}` escapes export root") from None


# ---------------------------------------------------------------------------
# local source tree validation (Round-2 amendment 4)
# ---------------------------------------------------------------------------


def _validate_local_tree(path: Path) -> None:
    for entry in path.rglob("*"):
        if entry.is_symlink():
            raise GitOpsError(f"local pack source contains a symlink `{entry}` — refusing")


# ---------------------------------------------------------------------------
# source_checkout
# ---------------------------------------------------------------------------


def _export_dir_name(url: str, commit: str, subdir: str) -> str:
    url_hash = hashlib.sha256(_normalize_url(url).encode("utf-8")).hexdigest()[:16]
    subdir_hash = hashlib.sha256(subdir.encode("utf-8")).hexdigest()[:16]
    return f"{url_hash}-{commit}-{subdir_hash}-{EXPORT_FORMAT}"


def source_checkout(source: PackSource, cache_dir: Path) -> tuple[Path, str]:
    """Resolve `source` to a usable filesystem path.

    local sources: validated for symlinks anywhere in the tree (Round-2
    amendment 4), returned as-is: (path, "local").

    git sources: mirrored + exported into
    `cache_dir/exports/<urlhash>-<commit>-<subdirhash>-v1/`, with a
    `.complete` marker written last, under the repo's mirror lock. A dir
    without the marker is wiped and re-exported; with the marker it's reused
    untouched.
    """
    cache_dir = Path(cache_dir)

    if source.local_path is not None:
        local_path = Path(source.local_path)
        if not local_path.exists():
            raise GitOpsError(f"local pack source `{local_path}` does not exist")
        _validate_local_tree(local_path)
        return local_path, "local"

    if not source.repo:
        raise GitOpsError("PackSource has neither `repo` nor `local_path` set")

    mirror = ensure_mirror(cache_dir, source.repo)
    lock_path = mirror.parent / (mirror.name + ".lock")

    with _locked(lock_path):
        commit = resolve_commit(mirror, source.ref)
        export_dir = cache_dir / "exports" / _export_dir_name(source.repo, commit, source.subdir)
        marker = export_dir / ".complete"

        if export_dir.exists() and not marker.exists():
            shutil.rmtree(export_dir)

        if not export_dir.exists():
            export_tree(mirror, commit, source.subdir, export_dir)
            marker.write_text("", encoding="utf-8")
            marker_fh = open(marker, "r+")
            try:
                marker_fh.flush()
                os.fsync(marker_fh.fileno())
            finally:
                marker_fh.close()

    return export_dir, "git"


# ---------------------------------------------------------------------------
# write primitives (v0.3 Phase B)
# ---------------------------------------------------------------------------


def fetch_default_branch(mirror: Path) -> tuple[str, str]:
    """Fetch the mirror's remote, return (branch_name, tip_commit_sha) for the
    repo's default branch. Re-resolves `origin/HEAD` freshly every call (a
    `--mirror` clone sets it at clone time, but `remote update` does not
    refresh it), falling back to `main` then `master` if it's stale/absent.
    Runs under the mirror's existing lock."""
    lock_path = mirror.parent / (mirror.name + ".lock")

    with _locked(lock_path):
        _git(["remote", "update", "--prune"], cwd=mirror)

        branch: str | None = None
        try:
            _git(["remote", "set-head", "origin", "-a"], cwd=mirror)
            symref = _git(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=mirror).strip()
            # format: refs/remotes/origin/<branch>
            prefix = "refs/remotes/origin/"
            if symref.startswith(prefix):
                branch = symref[len(prefix) :]
        except GitOpsError:
            branch = None

        if not branch:
            for candidate in ("main", "master"):
                try:
                    _git(["rev-parse", "--verify", f"refs/heads/{candidate}"], cwd=mirror)
                    branch = candidate
                    break
                except GitOpsError:
                    continue

        if not branch:
            raise GitOpsError(
                "could not determine default branch: origin/HEAD unset and neither "
                "`main` nor `master` exist"
            )

        tip_sha = resolve_commit(mirror, branch)

    return branch, tip_sha


def create_worktree(mirror: Path, branch: str, worktrees_dir: Path) -> Path:
    """`git worktree add <fresh-dir> <branch>` cut from `mirror`, into a
    freshly-created dir under `worktrees_dir` (name includes a uuid — never
    reused). Returns the worktree path. Caller owns cleanup via
    `remove_worktree`."""
    lock_path = mirror.parent / (mirror.name + ".lock")

    worktrees_dir = Path(worktrees_dir)
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    worktree = worktrees_dir / f"{branch}-{uuid.uuid4().hex}"

    with _locked(lock_path):
        _git(["worktree", "add", str(worktree), branch], cwd=mirror)

    return worktree


def remove_worktree(mirror: Path, worktree: Path) -> None:
    """`git worktree remove --force <worktree>` then `git worktree prune`,
    best-effort (never raises — cleanup-on-error paths must never mask the
    original error)."""
    try:
        _git(["worktree", "remove", "--force", str(worktree)], cwd=mirror)
    except GitOpsError:
        pass
    try:
        shutil.rmtree(worktree, ignore_errors=True)
    except OSError:
        pass
    try:
        _git(["worktree", "prune"], cwd=mirror)
    except GitOpsError:
        pass


def check_identity(worktree: Path) -> None:
    """Verify `git config user.name` and `user.email` resolve (worktree or
    global config) — raise GitOpsError naming which is missing, before any
    commit is attempted."""
    missing: list[str] = []
    for key in ("user.name", "user.email"):
        try:
            value = _git(["config", "--get", key], cwd=worktree).strip()
        except GitOpsError:
            value = ""
        if not value:
            missing.append(key)

    if missing:
        raise GitOpsError(
            f"git identity not configured: missing {', '.join(missing)} "
            f"(set via `git config user.name`/`user.email`, worktree or global)"
        )


def commit_all(worktree: Path, message: str) -> str:
    """`git add -A` + `git commit -m <message>` in the worktree; returns the
    new commit sha. Raises GitOpsError if there is nothing to commit."""
    _git(["add", "-A"], cwd=worktree)

    status = _git(["status", "--porcelain"], cwd=worktree)
    if not status.strip():
        raise GitOpsError("nothing to commit: worktree has no staged changes")

    _git(["commit", "-m", message], cwd=worktree)
    sha = _git(["rev-parse", "HEAD"], cwd=worktree).strip()
    return sha


def push_fast_forward(mirror: Path, worktree: Path, branch: str) -> None:
    """Push `worktree`'s branch to `mirror`'s `origin` remote, fast-forward
    only (plain `git push origin <branch>`, non-FF-safe by default). On
    rejection, raise GitOpsError with the real git stderr, distinguishing a
    non-fast-forward rejection (message contains "non-fast-forward" or
    "fetch first") from other failures."""
    try:
        # The worktree's `origin` remote config is inherited from the
        # `--mirror` clone (`remote.origin.mirror = true`), which forbids
        # any explicit refspec on push. Override it for this one push —
        # the worktree itself is a plain (non-mirror) checkout, we just
        # want a normal fast-forward-checked push of a single branch.
        _git(
            ["-c", "remote.origin.mirror=false", "push", "origin", f"{branch}:{branch}"],
            cwd=worktree,
        )
    except GitOpsError as exc:
        message = str(exc)
        lowered = message.lower()
        if "non-fast-forward" in lowered or "fetch first" in lowered:
            raise GitOpsError(
                f"push rejected (non-fast-forward): upstream has moved — {message}"
            ) from None
        raise


def push_branch(worktree: Path, remote_url: str, local_branch: str, remote_branch: str) -> None:
    """Push `local_branch` to `remote_url` as `remote_branch` (creates it) —
    used by the --pr path to push a feature branch DIRECTLY to the real
    origin (not the mirror). Fails loudly (GitOpsError) on any rejection —
    no force."""
    _git(["push", remote_url, f"{local_branch}:{remote_branch}"], cwd=worktree)


def set_remote_url(worktree: Path, remote_name: str, url: str) -> None:
    """`git remote set-url <remote_name> <url>` in the worktree."""
    _git(["remote", "set-url", remote_name, url], cwd=worktree)


def staged_diff(worktree: Path) -> str:
    """Stage all changes (`git add -A`) then return `git diff --cached`
    output. Callers that go on to commit should call `commit_all` next,
    which re-runs `git add -A` (idempotent) before committing."""
    _git(["add", "-A"], cwd=worktree)
    return _git(["diff", "--cached"], cwd=worktree)


def open_pr(repo_url: str, head_branch: str, base_branch: str, title: str, body: str) -> str:
    """Open a PR via `gh pr create --repo ... --head ... --base ... --title
    ... --body ... --json url -q .url`. Wrapped like `_git()` — stderr is
    captured into GitOpsError, including "gh: command not found" and `gh`
    auth failures surfaced verbatim."""
    args = [
        "gh",
        "pr",
        "create",
        "--repo",
        repo_url,
        "--head",
        head_branch,
        "--base",
        base_branch,
        "--title",
        title,
        "--body",
        body,
        "--json",
        "url",
        "-q",
        ".url",
    ]
    try:
        result = subprocess.run(
            args,
            cwd=None,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise GitOpsError(f"gh pr create failed: {stderr}") from None
    except FileNotFoundError as exc:
        raise GitOpsError(f"gh executable not found: {exc}") from None
    return result.stdout.strip()

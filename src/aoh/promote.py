from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from aoh import gitops, paths
from aoh.pack import load_pack, validate_pack
from aoh.site import PackSource
from aoh.skillcopy import SkillCopyError, copy_skill_tree


class PromoteError(ValueError):
    """Raised when a skill promotion operation fails (git/copy-hygiene
    errors) — distinct from `PackError`, which surfaces pack *validation*
    failures unwrapped."""


@dataclass(frozen=True)
class PromoteResult:
    status: str  # "committed" | "pr_opened" | "noop"
    sha: str | None  # commit sha (committed/noop) or None (pr_opened uses branch instead)
    branch: str | None  # set only for pr_opened
    pr_url: str | None  # set only for pr_opened
    staged_diff: str  # `git diff --cached` shown before the commit decision; "" for noop


def discover_skill_source(name: str, from_dir: Path | None, cwd: Path) -> Path:
    """If `from_dir` given, return it (must contain SKILL.md, else
    PromoteError). Otherwise search upward from `cwd` for the first of
    `.claude/skills/<name>/SKILL.md` or `.agents/skills/<name>/SKILL.md`,
    checked at EVERY directory level (`.claude` before `.agents` at each
    level) before ascending — so the search stops at the first match walking
    upward, never mixing levels."""
    if from_dir is not None:
        if not (from_dir / "SKILL.md").exists():
            raise PromoteError(f"`{from_dir}` does not contain SKILL.md — not a valid skill draft")
        return from_dir

    tried: list[str] = []
    current = cwd.resolve()
    while True:
        for kind in (".claude", ".agents"):
            candidate = current / kind / "skills" / name
            tried.append(str(candidate))
            if (candidate / "SKILL.md").exists():
                return candidate

        parent = current.parent
        if parent == current:
            break
        current = parent

    raise PromoteError(
        f"could not find skill `{name}` — tried: " + ", ".join(tried)
    )


def promote_skill(
    *,
    name: str,
    from_dir: Path | None,
    pack_source: PackSource,
    cache_dir: Path,
    pr: bool = False,
    cwd: Path | None = None,
) -> PromoteResult:
    source = discover_skill_source(name, from_dir, cwd or Path.cwd())

    if pack_source.local_path is not None:
        raise PromoteError(
            "promote requires a git-backed pack — this pack source is a local path"
        )

    mirror = gitops.ensure_mirror(cache_dir, pack_source.repo)
    branch, _base_sha = gitops.fetch_default_branch(mirror)
    worktree = gitops.create_worktree(mirror, branch, cache_dir / "worktrees")

    try:
        # Repoint the worktree's `origin` to the REAL remote
        # (`pack_source.repo`) exactly once, immediately after worktree
        # creation. The worktree's `origin` is inherited from the mirror's
        # `--mirror` clone config, which points at the real repo URL already
        # but carries `remote.origin.mirror = true` (forbids explicit
        # refspecs). From this point on, EVERY push from this worktree
        # (push_fast_forward's `git push origin ...` on the direct-commit
        # path, or push_branch's explicit-URL push of a NEW feature branch
        # on the --pr path) goes to `pack_source.repo` — never to the
        # mirror. This is deliberate: it's what makes push_fast_forward's
        # fast-forward check meaningful (checked against the real remote's
        # live tip, not a stale mirror), and it means push_branch always
        # passes the URL explicitly too, per the hard rule that this
        # worktree must NEVER push through the remote NAME "origin" once
        # `set_remote_url` has been called with a value other than the
        # mirror path. This call must run INSIDE the try/finally (not
        # before it) so a failure here (disk-full, permissions, corrupted
        # worktree git-config) still triggers `remove_worktree` cleanup
        # below, instead of leaking the worktree dir and its git-worktree
        # registration.
        gitops.set_remote_url(worktree, "origin", pack_source.repo)

        gitops.check_identity(worktree)

        dest = paths.safe_join(worktree, "skills", paths.safe_segment("skill", name))
        if dest.exists():
            shutil.rmtree(dest)
        try:
            copy_skill_tree(source, dest)
        except SkillCopyError as exc:
            raise PromoteError(str(exc)) from exc

        pack = load_pack(worktree)
        validate_pack(pack)

        diff = gitops.staged_diff(worktree)

        try:
            sha = gitops.commit_all(
                worktree, f"feat(skill): add {name} (promoted from local draft)"
            )
        except gitops.GitOpsError as exc:
            if "nothing to commit" in str(exc).lower():
                head_sha = gitops.resolve_commit(worktree, "HEAD")
                return PromoteResult(
                    status="noop",
                    sha=head_sha,
                    branch=None,
                    pr_url=None,
                    staged_diff="",
                )
            raise PromoteError(str(exc)) from exc

        if not pr:
            try:
                gitops.push_fast_forward(mirror, worktree, branch)
            except gitops.GitOpsError as exc:
                message = str(exc)
                lowered = message.lower()
                if "non-fast-forward" in lowered or "fetch first" in lowered:
                    raise PromoteError(
                        "upstream has moved since this promotion started — re-run with --pr"
                    ) from None
                raise PromoteError(message) from exc

            # No further push here: `push_fast_forward` already pushed
            # `branch` to `origin`, which `set_remote_url` repointed to the
            # real `pack_source.repo` — the commit is already on the real
            # remote. `push_branch` is only needed for the --pr path below,
            # where it publishes a NEW feature branch that
            # `push_fast_forward` never touches.
            return PromoteResult(
                status="committed",
                sha=sha,
                branch=None,
                pr_url=None,
                staged_diff=diff,
            )
        else:
            feature_branch = f"skill/{name}"
            try:
                gitops.create_branch(worktree, feature_branch)
            except gitops.GitOpsError as exc:
                raise PromoteError(str(exc)) from exc

            try:
                gitops.push_branch(worktree, pack_source.repo, feature_branch, feature_branch)
            except gitops.GitOpsError as exc:
                raise PromoteError(str(exc)) from exc

            try:
                pr_url = gitops.open_pr(
                    pack_source.repo,
                    feature_branch,
                    branch,
                    f"feat(skill): add {name}",
                    f"Promoted `{name}` from a local draft via `aoh skill promote`.",
                )
            except gitops.GitOpsError as exc:
                raise PromoteError(str(exc)) from exc

            return PromoteResult(
                status="pr_opened",
                sha=None,
                branch=feature_branch,
                pr_url=pr_url,
                staged_diff=diff,
            )
    finally:
        gitops.remove_worktree(mirror, worktree)

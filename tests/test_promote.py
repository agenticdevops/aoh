from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.pack import PackError
from aoh.promote import PromoteError, PromoteResult, discover_skill_source, promote_skill
from aoh.site import PackSource


# ---------------------------------------------------------------------------
# fixture helpers (mirrors tests/test_gitops.py conventions)
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


def _seed_minimal_pack(work: Path) -> None:
    write(
        work / "AOH.yaml",
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Pack
        metadata:
          name: demo
          displayName: Demo
          description: Minimal demo pack for promote tests.
          owner: Test
        """,
    )
    write(
        work / "skills" / "existing-skill" / "SKILL.md",
        """
        ---
        name: existing-skill
        description: Use when demoing promote's existing pack content.
        ---

        # Existing Skill

        Placeholder body.
        """,
    )


def make_bare_repo(tmp_path: Path, name: str = "origin.git") -> Path:
    """Bare repo seeded with a minimal valid v1alpha2 pack at the repo root
    (promote_skill treats the worktree root as the pack root)."""
    bare = tmp_path / name
    _run(["git", "init", "--bare", "-q", str(bare)], cwd=tmp_path)

    work = tmp_path / f"_seed-{name}"
    _run(["git", "init", "-q", str(work)], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "Test"], cwd=work)

    _seed_minimal_pack(work)

    _run(["git", "add", "-A"], cwd=work)
    _run(["git", "commit", "-q", "-m", "seed"], cwd=work)
    _run(["git", "remote", "add", "origin", str(bare)], cwd=work)
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)

    return bare


def bare_repo_url(bare: Path) -> str:
    return f"file://{bare}"


def fresh_clone(bare: Path, tmp_path: Path, dest_name: str = "_verify") -> Path:
    """Clone the bare origin fresh, to inspect its real state independent of
    any mirror cache."""
    dest = tmp_path / dest_name
    if dest.exists():
        import shutil

        shutil.rmtree(dest)
    _run(["git", "clone", "-q", str(bare), str(dest)], cwd=tmp_path)
    return dest


def commit_extra(bare: Path, tmp_path: Path, filename: str = "extra.txt") -> str:
    """Simulate someone else pushing directly to origin's main."""
    work = tmp_path / f"_extra-{filename.replace('/', '_')}"
    _run(["git", "clone", "-q", str(bare), str(work)], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "Test"], cwd=work)
    write(work / filename, "extra content")
    _run(["git", "add", "-A"], cwd=work)
    _run(["git", "commit", "-q", "-m", "extra"], cwd=work)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=work).stdout.strip()
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)
    return sha


def make_draft(
    tmp_path: Path,
    name: str = "new-skill",
    dirname: str | None = None,
    executable_script: bool = True,
) -> Path:
    """A local skill draft dir with SKILL.md + an executable script."""
    draft = tmp_path / "draft" / (dirname or name)
    write(
        draft / "SKILL.md",
        f"""
        ---
        name: {name}
        description: Use when testing promote of {name}.
        ---

        # {name}

        Draft skill body.
        """,
    )
    script = draft / "scripts" / "run.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    if executable_script:
        script.chmod(0o755)
    return draft


def make_broken_draft(tmp_path: Path, name: str = "broken-skill") -> Path:
    """Draft whose SKILL.md frontmatter name does not match the dir name —
    a validation failure the pack loader will catch (frontmatter name
    mismatch), but only once copied to a proper `skills/<name>` dest."""
    draft = tmp_path / "draft-broken" / name
    write(
        draft / "SKILL.md",
        f"""
        ---
        name: totally-different-name
        description: Use when testing broken frontmatter.
        ---

        # {name}

        Draft skill body with mismatched frontmatter name.
        """,
    )
    return draft


def make_symlink_draft(tmp_path: Path, name: str = "symlink-skill") -> Path:
    draft = tmp_path / "draft-symlink" / name
    write(
        draft / "SKILL.md",
        f"""
        ---
        name: {name}
        description: Use when testing symlink refusal.
        ---

        # {name}

        Draft body.
        """,
    )
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (draft / "evil-link").symlink_to(outside)
    return draft


def pack_source_for(bare: Path) -> PackSource:
    return PackSource(repo=bare_repo_url(bare), subdir="", ref="HEAD", local_path=None)


# ---------------------------------------------------------------------------
# discover_skill_source
# ---------------------------------------------------------------------------


def test_discover_skill_source_from_dir_wins_outright(tmp_path: Path) -> None:
    explicit = make_draft(tmp_path, name="explicit-skill")
    # also create an upward-discoverable one that should be ignored
    cwd = tmp_path / "project"
    write(
        cwd / ".claude" / "skills" / "explicit-skill" / "SKILL.md",
        """
        ---
        name: explicit-skill
        description: Should not be used.
        ---

        # decoy
        """,
    )

    found = discover_skill_source("explicit-skill", explicit, cwd)

    assert found == explicit


def test_discover_skill_source_from_dir_missing_skill_md_raises(tmp_path: Path) -> None:
    bad_dir = tmp_path / "not-a-skill"
    bad_dir.mkdir()

    with pytest.raises(PromoteError):
        discover_skill_source("whatever", bad_dir, tmp_path)


def test_discover_skill_source_upward_search_finds_claude_two_levels_up(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    write(
        root / ".claude" / "skills" / "my-skill" / "SKILL.md",
        """
        ---
        name: my-skill
        description: Use when testing upward discovery.
        ---

        # my-skill
        """,
    )
    cwd = root / "a" / "b"
    cwd.mkdir(parents=True)

    found = discover_skill_source("my-skill", None, cwd)

    assert found == root / ".claude" / "skills" / "my-skill"


def test_discover_skill_source_claude_beats_agents_at_same_level(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    write(
        root / ".claude" / "skills" / "dual-skill" / "SKILL.md",
        """
        ---
        name: dual-skill
        description: The .claude version — must win.
        ---

        # dual-skill (claude)
        """,
    )
    write(
        root / ".agents" / "skills" / "dual-skill" / "SKILL.md",
        """
        ---
        name: dual-skill
        description: The .agents version — must lose.
        ---

        # dual-skill (agents)
        """,
    )

    found = discover_skill_source("dual-skill", None, root)

    assert found == root / ".claude" / "skills" / "dual-skill"


def test_discover_skill_source_never_mixes_levels(tmp_path: Path) -> None:
    """A closer `.agents/skills/<name>` must win over a farther
    `.claude/skills/<name>` — the search stops at the first match walking
    upward, never mixing levels."""
    root = tmp_path / "proj"
    write(
        root / ".claude" / "skills" / "mix-skill" / "SKILL.md",
        """
        ---
        name: mix-skill
        description: Farther .claude version — must lose.
        ---

        # mix-skill (far claude)
        """,
    )
    nested = root / "sub"
    write(
        nested / ".agents" / "skills" / "mix-skill" / "SKILL.md",
        """
        ---
        name: mix-skill
        description: Closer .agents version — must win.
        ---

        # mix-skill (near agents)
        """,
    )

    found = discover_skill_source("mix-skill", None, nested)

    assert found == nested / ".agents" / "skills" / "mix-skill"


def test_discover_skill_source_neither_found_raises_naming_both_paths(tmp_path: Path) -> None:
    cwd = tmp_path / "empty-project"
    cwd.mkdir()

    with pytest.raises(PromoteError) as excinfo:
        discover_skill_source("missing-skill", None, cwd)

    message = str(excinfo.value)
    assert ".claude/skills/missing-skill" in message
    assert ".agents/skills/missing-skill" in message


# ---------------------------------------------------------------------------
# promote_skill — requires git-backed pack
# ---------------------------------------------------------------------------


def test_promote_skill_requires_git_backed_pack(tmp_path: Path) -> None:
    draft = make_draft(tmp_path)
    local_pack_source = PackSource(repo=None, subdir="", ref="HEAD", local_path=tmp_path / "local-pack")

    with pytest.raises(PromoteError):
        promote_skill(
            name="new-skill",
            from_dir=draft,
            pack_source=local_pack_source,
            cache_dir=tmp_path / "cache",
        )


# ---------------------------------------------------------------------------
# promote_skill — direct-commit happy path
# ---------------------------------------------------------------------------


def test_promote_skill_direct_commit_happy_path(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    draft = make_draft(tmp_path, name="new-skill")
    cache_dir = tmp_path / "cache"

    result = promote_skill(
        name="new-skill",
        from_dir=draft,
        pack_source=pack_source_for(bare),
        cache_dir=cache_dir,
    )

    assert isinstance(result, PromoteResult)
    assert result.status == "committed"
    assert result.sha is not None
    assert result.branch is None
    assert result.pr_url is None
    assert "new-skill" in result.staged_diff
    assert "SKILL.md" in result.staged_diff

    # verify via a FRESH clone of the bare origin (independent of any mirror
    # cache state)
    clone = fresh_clone(bare, tmp_path)
    log = _run(["git", "log", "--oneline"], cwd=clone).stdout
    assert result.sha[:7] in log or result.sha in _run(["git", "rev-parse", "HEAD"], cwd=clone).stdout
    assert (clone / "skills" / "new-skill" / "SKILL.md").exists()
    assert (clone / "skills" / "new-skill" / "scripts" / "run.sh").exists()

    # executable bit preserved
    mode = (clone / "skills" / "new-skill" / "scripts" / "run.sh").stat().st_mode
    assert mode & 0o111

    # worktree cleaned up
    cache_mirror_dirs = list((cache_dir).glob("*.git"))
    assert cache_mirror_dirs, "expected a mirror dir to exist"
    mirror = cache_mirror_dirs[0]
    worktree_listing = _run(["git", "worktree", "list"], cwd=mirror).stdout
    # only the mirror itself should be listed (bare has no listed worktree
    # path beyond the mirror root)
    lines = [line for line in worktree_listing.splitlines() if line.strip()]
    assert len(lines) == 1


def test_promote_skill_worktree_dir_removed_after_success(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    draft = make_draft(tmp_path, name="cleanup-skill")
    cache_dir = tmp_path / "cache"

    promote_skill(
        name="cleanup-skill",
        from_dir=draft,
        pack_source=pack_source_for(bare),
        cache_dir=cache_dir,
    )

    worktrees_dir = cache_dir / "worktrees"
    if worktrees_dir.exists():
        remaining = list(worktrees_dir.iterdir())
        assert remaining == []


def test_promote_skill_set_remote_url_failure_cleans_up_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If `gitops.set_remote_url` raises (disk-full, permissions, corrupted
    worktree git-config are realistic causes), the worktree created just
    before it must still be cleaned up — no stray `git worktree list` entry,
    no leftover directory under `cache_dir/worktrees/`."""
    bare = make_bare_repo(tmp_path)
    draft = make_draft(tmp_path, name="remote-url-fail-skill")
    cache_dir = tmp_path / "cache"

    import aoh.promote as promote_mod

    def fake_set_remote_url(worktree, remote_name, url):
        raise promote_mod.gitops.GitOpsError("boom")

    monkeypatch.setattr(promote_mod.gitops, "set_remote_url", fake_set_remote_url)

    # matches the existing convention for `check_identity` (also called
    # unwrapped as the first statement inside the try block): a GitOpsError
    # from a raw gitops call at the top of the try propagates as-is, it is
    # not wrapped in PromoteError.
    with pytest.raises(promote_mod.gitops.GitOpsError):
        promote_skill(
            name="remote-url-fail-skill",
            from_dir=draft,
            pack_source=pack_source_for(bare),
            cache_dir=cache_dir,
        )

    # (a) no stray worktree left in `git worktree list`
    cache_mirror_dirs = list(cache_dir.glob("*.git"))
    assert cache_mirror_dirs, "expected a mirror dir to exist"
    mirror = cache_mirror_dirs[0]
    worktree_listing = _run(["git", "worktree", "list"], cwd=mirror).stdout
    lines = [line for line in worktree_listing.splitlines() if line.strip()]
    assert len(lines) == 1

    # (b) the worktree directory itself no longer exists on disk
    worktrees_dir = cache_dir / "worktrees"
    if worktrees_dir.exists():
        remaining = list(worktrees_dir.iterdir())
        assert remaining == []


# ---------------------------------------------------------------------------
# promote_skill — validation-failure path
# ---------------------------------------------------------------------------


def test_promote_skill_validation_failure_before_any_commit(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    draft = make_broken_draft(tmp_path)
    cache_dir = tmp_path / "cache"

    clone_before = fresh_clone(bare, tmp_path, dest_name="_before")
    head_before = _run(["git", "rev-parse", "HEAD"], cwd=clone_before).stdout.strip()

    # PackError (pack validation failure) propagates as-is — it's a genuine
    # pack error, not a promote-operation error, so it is NOT wrapped in
    # PromoteError.
    with pytest.raises(PackError):
        promote_skill(
            name="broken-skill",
            from_dir=draft,
            pack_source=pack_source_for(bare),
            cache_dir=cache_dir,
        )

    clone_after = fresh_clone(bare, tmp_path, dest_name="_after")
    head_after = _run(["git", "rev-parse", "HEAD"], cwd=clone_after).stdout.strip()

    assert head_before == head_after


def test_promote_skill_validation_failure_cleans_up_worktree(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    draft = make_broken_draft(tmp_path)
    cache_dir = tmp_path / "cache"

    with pytest.raises(PackError):
        promote_skill(
            name="broken-skill",
            from_dir=draft,
            pack_source=pack_source_for(bare),
            cache_dir=cache_dir,
        )

    cache_mirror_dirs = list(cache_dir.glob("*.git"))
    assert cache_mirror_dirs
    mirror = cache_mirror_dirs[0]
    worktree_listing = _run(["git", "worktree", "list"], cwd=mirror).stdout
    lines = [line for line in worktree_listing.splitlines() if line.strip()]
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# promote_skill — no-op re-promote
# ---------------------------------------------------------------------------


def test_promote_skill_noop_on_identical_reprepromote(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    draft = make_draft(tmp_path, name="idempotent-skill")
    cache_dir = tmp_path / "cache"

    first = promote_skill(
        name="idempotent-skill",
        from_dir=draft,
        pack_source=pack_source_for(bare),
        cache_dir=cache_dir,
    )
    assert first.status == "committed"

    clone_after_first = fresh_clone(bare, tmp_path, dest_name="_after_first")
    head_after_first = _run(["git", "rev-parse", "HEAD"], cwd=clone_after_first).stdout.strip()

    second = promote_skill(
        name="idempotent-skill",
        from_dir=draft,
        pack_source=pack_source_for(bare),
        cache_dir=cache_dir,
    )

    assert second.status == "noop"
    assert second.sha == first.sha
    assert second.staged_diff == ""

    clone_after_second = fresh_clone(bare, tmp_path, dest_name="_after_second")
    head_after_second = _run(["git", "rev-parse", "HEAD"], cwd=clone_after_second).stdout.strip()

    assert head_after_first == head_after_second


def test_promote_skill_update_in_place_on_changed_reprepromote(tmp_path: Path) -> None:
    """Re-promoting an ALREADY-promoted skill whose local draft content has
    since CHANGED (not identical) must land a NEW commit with the updated
    content — not a noop."""
    bare = make_bare_repo(tmp_path)
    draft = make_draft(tmp_path, name="updatable-skill")

    cache_dir = tmp_path / "cache"

    first = promote_skill(
        name="updatable-skill",
        from_dir=draft,
        pack_source=pack_source_for(bare),
        cache_dir=cache_dir,
    )
    assert first.status == "committed"

    clone_after_first = fresh_clone(bare, tmp_path, dest_name="_after_first_update")
    first_body = (clone_after_first / "skills" / "updatable-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Draft skill body." in first_body
    assert "Now with an extra line." not in first_body

    # modify the local draft's SKILL.md content (add a line to the body)
    skill_md = draft / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8") + "\nNow with an extra line.\n",
        encoding="utf-8",
    )

    second = promote_skill(
        name="updatable-skill",
        from_dir=draft,
        pack_source=pack_source_for(bare),
        cache_dir=cache_dir,
    )

    # not a noop — a real commit landed
    assert second.status == "committed"
    assert second.sha is not None
    assert second.sha != first.sha
    assert "SKILL.md" in second.staged_diff

    # verify via a FRESH clone that the new content is actually there (not
    # just a new sha)
    clone_after_second = fresh_clone(bare, tmp_path, dest_name="_after_second_update")
    second_body = (clone_after_second / "skills" / "updatable-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Now with an extra line." in second_body

    # sanity check the diff/commit only reflects the actual changed content
    # — the unrelated script file should be untouched
    log = _run(
        ["git", "show", "--stat", "--oneline", second.sha], cwd=clone_after_second
    ).stdout
    assert "SKILL.md" in log
    assert "run.sh" not in log


# ---------------------------------------------------------------------------
# promote_skill — conflict detection
# ---------------------------------------------------------------------------


def test_promote_skill_conflict_raises_with_pr_suggestion_and_cleans_up(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    draft1 = make_draft(tmp_path, name="first-skill")
    draft2 = make_draft(tmp_path, name="second-skill", dirname="second-skill-dir")
    cache_dir = tmp_path / "cache"

    first = promote_skill(
        name="first-skill",
        from_dir=draft1,
        pack_source=pack_source_for(bare),
        cache_dir=cache_dir,
    )
    assert first.status == "committed"

    # Simulate someone else pushing directly to origin's main via a separate
    # tracking clone, BEFORE the second promote's push lands.
    import aoh.gitops as gitops_mod

    real_push_fast_forward = gitops_mod.push_fast_forward

    def intercepted_push_fast_forward(mirror, worktree, branch):
        commit_extra(bare, tmp_path, filename="someone-else-was-here.txt")
        return real_push_fast_forward(mirror, worktree, branch)

    import aoh.promote as promote_mod

    original = promote_mod.gitops.push_fast_forward
    promote_mod.gitops.push_fast_forward = intercepted_push_fast_forward
    try:
        with pytest.raises(PromoteError) as excinfo:
            promote_skill(
                name="second-skill",
                from_dir=draft2,
                pack_source=pack_source_for(bare),
                cache_dir=cache_dir,
            )
    finally:
        promote_mod.gitops.push_fast_forward = original

    assert "--pr" in str(excinfo.value)

    cache_mirror_dirs = list(cache_dir.glob("*.git"))
    assert cache_mirror_dirs
    mirror = cache_mirror_dirs[0]
    worktree_listing = _run(["git", "worktree", "list"], cwd=mirror).stdout
    lines = [line for line in worktree_listing.splitlines() if line.strip()]
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# promote_skill — --pr path
# ---------------------------------------------------------------------------


def test_promote_skill_pr_path_pushes_branch_and_calls_open_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = make_bare_repo(tmp_path)
    draft = make_draft(tmp_path, name="pr-skill")
    cache_dir = tmp_path / "cache"

    clone_before = fresh_clone(bare, tmp_path, dest_name="_before_pr")
    head_before = _run(["git", "rev-parse", "HEAD"], cwd=clone_before).stdout.strip()

    import aoh.promote as promote_mod

    captured: dict[str, object] = {}

    def fake_open_pr(repo_url, head_branch, base_branch, title, body):
        captured["repo_url"] = repo_url
        captured["head_branch"] = head_branch
        captured["base_branch"] = base_branch
        return "https://github.com/acme/repo/pull/42"

    monkeypatch.setattr(promote_mod.gitops, "open_pr", fake_open_pr)

    result = promote_skill(
        name="pr-skill",
        from_dir=draft,
        pack_source=pack_source_for(bare),
        cache_dir=cache_dir,
        pr=True,
    )

    assert result.status == "pr_opened"
    assert result.pr_url == "https://github.com/acme/repo/pull/42"
    assert result.branch == "skill/pr-skill"
    assert result.sha is None

    # branch pushed to the real origin with the right commit
    branch_sha = _run(["git", "rev-parse", "skill/pr-skill"], cwd=bare).stdout.strip()
    assert branch_sha

    # default branch (main) unchanged
    clone_after = fresh_clone(bare, tmp_path, dest_name="_after_pr")
    head_after = _run(["git", "rev-parse", "HEAD"], cwd=clone_after).stdout.strip()
    assert head_before == head_after

    assert captured["head_branch"] == "skill/pr-skill"
    assert captured["base_branch"] == "main"


# ---------------------------------------------------------------------------
# promote_skill — copy-hygiene passthrough
# ---------------------------------------------------------------------------


def test_promote_skill_symlink_draft_surfaces_as_promote_error(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    draft = make_symlink_draft(tmp_path)
    cache_dir = tmp_path / "cache"

    clone_before = fresh_clone(bare, tmp_path, dest_name="_before_symlink")
    head_before = _run(["git", "rev-parse", "HEAD"], cwd=clone_before).stdout.strip()

    with pytest.raises(PromoteError):
        promote_skill(
            name="symlink-skill",
            from_dir=draft,
            pack_source=pack_source_for(bare),
            cache_dir=cache_dir,
        )

    clone_after = fresh_clone(bare, tmp_path, dest_name="_after_symlink")
    head_after = _run(["git", "rev-parse", "HEAD"], cwd=clone_after).stdout.strip()
    assert head_before == head_after

    cache_mirror_dirs = list(cache_dir.glob("*.git"))
    assert cache_mirror_dirs
    mirror = cache_mirror_dirs[0]
    worktree_listing = _run(["git", "worktree", "list"], cwd=mirror).stdout
    lines = [line for line in worktree_listing.splitlines() if line.strip()]
    assert len(lines) == 1

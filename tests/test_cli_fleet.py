"""CLI fleet surface: `aoh install --site` fan-out, `aoh list`, `aoh config`,
`aoh lock`.

Covers the v0.3 Phase A Task 6 RED list: lock-required install, F1
(locked-commit installs survive an upstream branch move), lock refusal on
changed source without --update, mode exclusivity (legacy vs site), list
fallback to configured site, per-binding failure isolation, config
init/get/set roundtrip, AOH_HOME-awareness.
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

from aoh.cli import main
from aoh.manifest import read_manifest
from aoh.pack import Binding
from aoh.site import Site, load_site_lock

KUBEOPS_PACK = PROJECT_ROOT / "collections/core/kubeops"


# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def make_bare_repo(tmp_path: Path, name: str = "origin.git") -> Path:
    """Bare repo seeded with a copy of the real kubeops pack at
    `collections/core/kubeops`, committed to `main`."""
    bare = tmp_path / name
    _run(["git", "init", "--bare", "-q", str(bare)], cwd=tmp_path)

    work = tmp_path / f"_seed-{name}"
    work.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q", str(work)], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "Test"], cwd=work)

    import shutil

    dest = work / "collections/core/kubeops"
    shutil.copytree(KUBEOPS_PACK, dest)

    _run(["git", "add", "-A"], cwd=work)
    _run(["git", "commit", "-q", "-m", "seed"], cwd=work)
    _run(["git", "remote", "add", "origin", str(bare)], cwd=work)
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)

    return bare


def bare_repo_url(bare: Path) -> str:
    return f"file://{bare}"


def commit_extra(bare: Path, tmp_path: Path, filename: str = "extra.txt") -> str:
    """Clone, add a harmless file under the pack dir, commit, push to main.
    Returns the new commit sha. Simulates the branch moving after lock."""
    work = tmp_path / f"_extra-{filename.replace('/', '_')}"
    _run(["git", "clone", "-q", str(bare), str(work)], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "Test"], cwd=work)
    write(work / "collections/core/kubeops" / filename, "extra content")
    _run(["git", "add", "-A"], cwd=work)
    _run(["git", "commit", "-q", "-m", "extra"], cwd=work)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=work).stdout.strip()
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)
    return sha


BINDING_TARGET = {"kubeContext": "kind-demo", "namespace": "default"}


def write_binding_file(path: Path, name: str, **spec_overrides) -> Path:
    lines = [
        "apiVersion: openagentix.io/v1alpha2",
        "kind: Binding",
        "metadata:",
        f"  name: {name}",
        "spec:",
        f"  role: {spec_overrides.get('role', 'kubeops-copilot')}",
    ]
    if "pack" in spec_overrides:
        lines.append(f"  pack: {spec_overrides['pack']}")
    if "group" in spec_overrides:
        lines.append(f"  group: {spec_overrides['group']}")
    target = spec_overrides.get("target", BINDING_TARGET)
    lines.append("  target:")
    for k, v in target.items():
        lines.append(f"    {k}: {v}")
    write(path, "\n".join(lines))
    return path


def write_git_site(site_root: Path, repo_url: str, ref: str = "main", *, name: str = "myorg-ops-site") -> Path:
    path = site_root / "site.yaml"
    write(
        path,
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Site
        metadata:
          name: {name}
        spec:
          defaults:
            runtime: claude-code
          packs:
            kubeops: {{repo: {repo_url}, subdir: collections/core/kubeops, ref: {ref}}}
          bindingsDir: bindings/
        """,
    )
    return path


def write_local_site(site_root: Path, *, name: str = "myorg-ops-site", extra_spec: str = "") -> Path:
    path = site_root / "site.yaml"
    write(
        path,
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Site
        metadata:
          name: {name}
        spec:
          defaults:
            runtime: claude-code
          packs:
            kubeops: {str(KUBEOPS_PACK)}
          bindingsDir: bindings/
        {extra_spec}
        """,
    )
    return path


def write_local_site_with_group(site_root: Path, *, name: str = "myorg-ops-site") -> Path:
    path = site_root / "site.yaml"
    write(
        path,
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Site
        metadata:
          name: {name}
        spec:
          defaults:
            runtime: claude-code
          packs:
            kubeops: {str(KUBEOPS_PACK)}
          groups:
            prod:
              vars: {{}}
          bindingsDir: bindings/
        """,
    )
    return path


# ---------------------------------------------------------------------------
# aoh lock — F1 minimal lock semantics
# ---------------------------------------------------------------------------


def test_lock_creates_lock_file_with_resolved_commit(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    site_root = tmp_path / "site"
    write_git_site(site_root, bare_repo_url(bare))
    write_binding_file(site_root / "bindings" / "kubeops-sresquad.yaml", "kubeops-sresquad")

    exit_code = main(["lock", "--site", str(site_root)])
    assert exit_code == 0

    lock = load_site_lock(site_root)
    assert lock is not None
    assert lock.packs["kubeops"].resolved_commit is not None
    assert lock.packs["kubeops"].requested_ref == "main"


def test_lock_records_local_source_uniformly(tmp_path: Path) -> None:
    site_root = tmp_path / "site"
    write_local_site(site_root)
    write_binding_file(site_root / "bindings" / "kubeops-sresquad.yaml", "kubeops-sresquad")

    exit_code = main(["lock", "--site", str(site_root)])
    assert exit_code == 0

    lock = load_site_lock(site_root)
    assert lock is not None
    assert lock.packs["kubeops"].local is True
    assert lock.packs["kubeops"].resolved_commit is None


def test_lock_initializes_only_never_moves_existing_entry(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    site_root = tmp_path / "site"
    write_git_site(site_root, bare_repo_url(bare))
    write_binding_file(site_root / "bindings" / "kubeops-sresquad.yaml", "kubeops-sresquad")

    assert main(["lock", "--site", str(site_root)]) == 0
    lock1 = load_site_lock(site_root)
    original_commit = lock1.packs["kubeops"].resolved_commit

    # Move `main` forward.
    commit_extra(bare, tmp_path)

    # Re-running `aoh lock` (no --update) must NOT move the existing entry —
    # it only initializes NEW entries.
    assert main(["lock", "--site", str(site_root)]) == 0
    lock2 = load_site_lock(site_root)
    assert lock2.packs["kubeops"].resolved_commit == original_commit


def test_lock_refuses_on_changed_source_without_update(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    site_root = tmp_path / "site"
    write_git_site(site_root, bare_repo_url(bare))
    write_binding_file(site_root / "bindings" / "kubeops-sresquad.yaml", "kubeops-sresquad")
    assert main(["lock", "--site", str(site_root)]) == 0

    # Change the requestedRef in site.yaml — lock now disagrees on ref.
    write_git_site(site_root, bare_repo_url(bare), ref="v9-does-not-exist")

    exit_code = main(["lock", "--site", str(site_root)])
    assert exit_code == 1


def test_lock_update_moves_commit_with_yes(tmp_path: Path) -> None:
    bare = make_bare_repo(tmp_path)
    site_root = tmp_path / "site"
    write_git_site(site_root, bare_repo_url(bare))
    write_binding_file(site_root / "bindings" / "kubeops-sresquad.yaml", "kubeops-sresquad")
    assert main(["lock", "--site", str(site_root)]) == 0
    old_commit = load_site_lock(site_root).packs["kubeops"].resolved_commit

    new_commit = commit_extra(bare, tmp_path)

    exit_code = main(["lock", "--site", str(site_root), "--update"])
    assert exit_code == 0

    lock = load_site_lock(site_root)
    assert lock.packs["kubeops"].resolved_commit == new_commit
    assert lock.packs["kubeops"].resolved_commit != old_commit


def test_lock_update_scoped_to_one_pack_name(tmp_path: Path) -> None:
    bare_a = make_bare_repo(tmp_path, name="a.git")
    bare_b = make_bare_repo(tmp_path, name="b.git")
    site_root = tmp_path / "site"
    write(
        site_root / "site.yaml",
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Site
        metadata:
          name: myorg-ops-site
        spec:
          packs:
            kubeops-a: {{repo: {bare_repo_url(bare_a)}, subdir: collections/core/kubeops, ref: main}}
            kubeops-b: {{repo: {bare_repo_url(bare_b)}, subdir: collections/core/kubeops, ref: main}}
          bindingsDir: bindings/
        """,
    )
    write_binding_file(site_root / "bindings" / "a-binding.yaml", "a-binding", pack="kubeops-a")
    write_binding_file(site_root / "bindings" / "b-binding.yaml", "b-binding", pack="kubeops-b")
    assert main(["lock", "--site", str(site_root)]) == 0

    old_a = load_site_lock(site_root).packs["kubeops-a"].resolved_commit
    old_b = load_site_lock(site_root).packs["kubeops-b"].resolved_commit

    new_a = commit_extra(bare_a, tmp_path, filename="only-a.txt")
    commit_extra(bare_b, tmp_path, filename="only-b.txt")  # b also moves, but is out of scope

    exit_code = main(["lock", "--site", str(site_root), "--update", "kubeops-a"])
    assert exit_code == 0

    lock = load_site_lock(site_root)
    assert lock.packs["kubeops-a"].resolved_commit == new_a
    assert lock.packs["kubeops-a"].resolved_commit != old_a
    # kubeops-b was NOT in the --update scope — untouched despite also moving.
    assert lock.packs["kubeops-b"].resolved_commit == old_b


# ---------------------------------------------------------------------------
# aoh install --site — fan-out, F1 lock-pinning
# ---------------------------------------------------------------------------


def test_install_site_without_lock_errors_naming_aoh_lock(tmp_path: Path, capsys) -> None:
    site_root = tmp_path / "site"
    write_local_site(site_root)
    write_binding_file(site_root / "bindings" / "kubeops-sresquad.yaml", "kubeops-sresquad")

    exit_code = main(
        ["install", "--site", str(site_root), "--workspace-root", str(tmp_path / "agents")]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "aoh lock" in captured.err


def test_install_site_fan_out_installs_all_bindings(tmp_path: Path) -> None:
    site_root = tmp_path / "site"
    write_local_site(site_root)
    write_binding_file(site_root / "bindings" / "alpha.yaml", "alpha")
    write_binding_file(site_root / "bindings" / "beta.yaml", "beta")
    assert main(["lock", "--site", str(site_root)]) == 0

    workspace_root = tmp_path / "agents"
    exit_code = main(
        ["install", "--site", str(site_root), "--workspace-root", str(workspace_root)]
    )

    assert exit_code == 0
    assert (workspace_root / "alpha" / "CLAUDE.md").exists()
    assert (workspace_root / "beta" / "CLAUDE.md").exists()


def test_install_site_single_binding_by_name(tmp_path: Path) -> None:
    site_root = tmp_path / "site"
    write_local_site(site_root)
    write_binding_file(site_root / "bindings" / "alpha.yaml", "alpha")
    write_binding_file(site_root / "bindings" / "beta.yaml", "beta")
    assert main(["lock", "--site", str(site_root)]) == 0

    workspace_root = tmp_path / "agents"
    exit_code = main(
        [
            "install",
            "--site",
            str(site_root),
            "--binding",
            "alpha",
            "--workspace-root",
            str(workspace_root),
        ]
    )

    assert exit_code == 0
    assert (workspace_root / "alpha" / "CLAUDE.md").exists()
    assert not (workspace_root / "beta").exists()


def test_install_site_group_filter(tmp_path: Path) -> None:
    site_root = tmp_path / "site"
    write_local_site_with_group(site_root)
    write_binding_file(site_root / "bindings" / "alpha.yaml", "alpha", group="prod")
    write_binding_file(site_root / "bindings" / "beta.yaml", "beta")
    assert main(["lock", "--site", str(site_root)]) == 0

    workspace_root = tmp_path / "agents"
    exit_code = main(
        [
            "install",
            "--site",
            str(site_root),
            "--group",
            "prod",
            "--workspace-root",
            str(workspace_root),
        ]
    )

    assert exit_code == 0
    assert (workspace_root / "alpha" / "CLAUDE.md").exists()
    assert not (workspace_root / "beta").exists()


def test_install_site_uses_locked_commit_not_moved_branch(tmp_path: Path) -> None:
    """The F1 test: after locking, moving the fixture repo's branch forward
    must NOT change what gets installed — the fan-out installs at the
    LOCK's resolvedCommit, never re-resolving the ref."""
    bare = make_bare_repo(tmp_path)
    site_root = tmp_path / "site"
    write_git_site(site_root, bare_repo_url(bare))
    write_binding_file(site_root / "bindings" / "kubeops-sresquad.yaml", "kubeops-sresquad")

    assert main(["lock", "--site", str(site_root)]) == 0
    locked_commit = load_site_lock(site_root).packs["kubeops"].resolved_commit

    # Move `main` forward — adds a new file to the pack tree post-lock.
    commit_extra(bare, tmp_path, filename="skills/pod-crashloop-triage/POST-LOCK-MARKER.txt")

    workspace_root = tmp_path / "agents"
    exit_code = main(
        ["install", "--site", str(site_root), "--workspace-root", str(workspace_root)]
    )
    assert exit_code == 0

    manifest = read_manifest(workspace_root / "kubeops-sresquad")
    assert manifest is not None
    assert manifest["resolvedCommit"] == locked_commit

    # The post-lock marker file must NOT be present anywhere in the pack
    # tree used — proof the moved branch had no effect.
    marker_hits = list(workspace_root.rglob("POST-LOCK-MARKER.txt"))
    assert marker_hits == []


def test_install_site_lock_disagreement_on_source_errors(tmp_path: Path) -> None:
    site_root = tmp_path / "site"
    write_local_site(site_root)
    write_binding_file(site_root / "bindings" / "kubeops-sresquad.yaml", "kubeops-sresquad")
    assert main(["lock", "--site", str(site_root)]) == 0

    # Repoint site.yaml's pack source somewhere else post-lock, without re-locking.
    other_local = tmp_path / "other-pack-copy"
    import shutil

    shutil.copytree(KUBEOPS_PACK, other_local)
    write_local_site(site_root)
    (site_root / "site.yaml").write_text(
        (site_root / "site.yaml").read_text(encoding="utf-8").replace(
            str(KUBEOPS_PACK), str(other_local)
        ),
        encoding="utf-8",
    )

    exit_code = main(
        ["install", "--site", str(site_root), "--workspace-root", str(tmp_path / "agents")]
    )
    assert exit_code == 1


def test_install_site_per_binding_failure_isolated(tmp_path: Path, capsys) -> None:
    site_root = tmp_path / "site"
    write_local_site(site_root)
    write_binding_file(site_root / "bindings" / "alpha.yaml", "alpha")
    # `beta`'s role does not exist in the pack — this binding will fail to
    # materialize (PackError) but must not stop `alpha` from installing.
    write_binding_file(
        site_root / "bindings" / "beta.yaml", "beta", role="nonexistent-role-xyz"
    )
    assert main(["lock", "--site", str(site_root)]) == 0

    workspace_root = tmp_path / "agents"
    exit_code = main(
        ["install", "--site", str(site_root), "--workspace-root", str(workspace_root)]
    )

    assert exit_code == 1
    assert (workspace_root / "alpha" / "CLAUDE.md").exists()
    # `beta` fails inside adapter.materialize (after install_workspace's
    # eager workspace.mkdir) — no CLAUDE.md or manifest ever lands there.
    assert not (workspace_root / "beta" / "CLAUDE.md").exists()
    assert read_manifest(workspace_root / "beta") is None
    captured = capsys.readouterr()
    assert "beta" in captured.err or "beta" in captured.out


def test_install_site_workspace_root_precedence_flag_wins(tmp_path: Path) -> None:
    site_root = tmp_path / "site"
    write_local_site(site_root)
    write_binding_file(site_root / "bindings" / "alpha.yaml", "alpha")
    assert main(["lock", "--site", str(site_root)]) == 0

    explicit_root = tmp_path / "explicit-agents"
    exit_code = main(
        ["install", "--site", str(site_root), "--workspace-root", str(explicit_root)]
    )
    assert exit_code == 0
    assert (explicit_root / "alpha").exists()


def test_install_site_accept_site_root_uses_advisory(tmp_path: Path, capsys) -> None:
    site_root = tmp_path / "site"
    advisory_root = tmp_path / "advisory-agents"
    write_local_site(site_root, extra_spec=f"  workspaceRoot: {advisory_root}\n")
    write_binding_file(site_root / "bindings" / "alpha.yaml", "alpha")
    assert main(["lock", "--site", str(site_root)]) == 0

    exit_code = main(["install", "--site", str(site_root), "--accept-site-root"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "workspace root" in (captured.err + captured.out).lower()
    assert (advisory_root / "alpha").exists()


def test_install_site_advisory_ignored_without_accept_flag_falls_back_to_home_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    site_root = tmp_path / "site"
    advisory_root = tmp_path / "advisory-agents"
    write_local_site(site_root, extra_spec=f"  workspaceRoot: {advisory_root}\n")
    write_binding_file(site_root / "bindings" / "alpha.yaml", "alpha")
    assert main(["lock", "--site", str(site_root)]) == 0

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # No --workspace-root and no --accept-site-root => falls back to
    # ~/agents default, NOT the site's advisory. A loud notice either way.
    exit_code = main(["install", "--site", str(site_root)])

    assert exit_code == 0
    captured = capsys.readouterr()
    combined = (captured.err + captured.out).lower()
    assert "workspace root" in combined
    assert "ignoring" in combined
    assert (fake_home / "agents" / "alpha").exists()
    assert not advisory_root.exists()


# ---------------------------------------------------------------------------
# aoh install — legacy/site mode exclusivity
# ---------------------------------------------------------------------------


def test_install_positional_pack_and_site_together_is_argparse_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "install",
                str(KUBEOPS_PACK),
                "--site",
                str(tmp_path / "site"),
                "--workspace-root",
                str(tmp_path / "agents"),
            ]
        )
    assert exc_info.value.code == 2


def test_install_site_mode_requires_no_positional_pack(tmp_path: Path) -> None:
    # Legacy mode still requires --runtime/--output; omitting --site and the
    # positional pack together is also invalid.
    with pytest.raises(SystemExit) as exc_info:
        main(["install", "--runtime", "claude-code", "--output", str(tmp_path / "out")])
    assert exc_info.value.code == 2


def test_install_legacy_mode_still_works_unchanged(tmp_path: Path) -> None:
    binding_file = tmp_path / "kubeops-sresquad.yaml"
    write_binding_file(binding_file, "kubeops-sresquad")

    exit_code = main(
        [
            "install",
            str(KUBEOPS_PACK),
            "--runtime",
            "claude-code",
            "--output",
            str(tmp_path / "workspace"),
            "--binding",
            str(binding_file),
        ]
    )
    assert exit_code == 0
    assert (tmp_path / "workspace" / ".claude" / "settings.json").exists()


# ---------------------------------------------------------------------------
# aoh list
# ---------------------------------------------------------------------------


def test_list_requires_site_or_configured_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    aoh_home = tmp_path / ".aoh-empty"
    monkeypatch.setenv("AOH_HOME", str(aoh_home))
    exit_code = main(["list"])
    assert exit_code == 1


def test_list_falls_back_to_configured_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    site_root = tmp_path / "site"
    write_local_site(site_root)
    write_binding_file(site_root / "bindings" / "alpha.yaml", "alpha")

    aoh_home = tmp_path / ".aoh"
    write(
        aoh_home / "config.yaml",
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: UserConfig
        site: {site_root}
        """,
    )
    monkeypatch.setenv("AOH_HOME", str(aoh_home))

    exit_code = main(["list"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "alpha" in captured.out


def test_list_explicit_site_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    site_root = tmp_path / "site"
    write_local_site(site_root)
    write_binding_file(site_root / "bindings" / "alpha.yaml", "alpha")
    monkeypatch.setenv("AOH_HOME", str(tmp_path / ".aoh-unused"))

    exit_code = main(["list", "--site", str(site_root)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "alpha" in captured.out
    assert "binding" in captured.out.lower()
    assert "role" in captured.out.lower()


def test_list_shows_provisioned_and_credential_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    site_root = tmp_path / "site"
    write_local_site(site_root)
    write_binding_file(site_root / "bindings" / "alpha.yaml", "alpha")
    assert main(["lock", "--site", str(site_root)]) == 0
    monkeypatch.setenv("AOH_HOME", str(tmp_path / ".aoh-unused"))

    workspace_root = tmp_path / "agents"
    assert (
        main(["install", "--site", str(site_root), "--workspace-root", str(workspace_root)])
        == 0
    )

    exit_code = main(["list", "--site", str(site_root), "--workspace-root", str(workspace_root)])
    assert exit_code == 0
    captured = capsys.readouterr()
    # Not provisioned yet (no kubeconfig/kubeconfig-overlay) => credential "-"
    assert "alpha" in captured.out


def test_list_never_resolves_workspace_path_outside_root_for_unsafe_binding_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    # Belt-and-suspenders: `load_site` now rejects `binding.name == ".."` at load
    # (see tests/test_site.py::test_load_site_rejects_dotdot_binding_name), so this
    # path can no longer be reached through real site.yaml + bindingsDir files.
    # But `_cmd_list` joins `workspace_root / binding.name` on whatever `Site` object
    # `load_site` returns — if a `Site` were ever hand-constructed or otherwise
    # produced with an unvalidated binding name (bypassing `load_site`'s file-based
    # loader), the join must still refuse to escape `workspace_root`, not silently
    # resolve a WORKSPACE path above it (raw `Path.__truediv__` happily resolves
    # `agents/..` to the parent of `agents/`).
    site_root = tmp_path / "site"
    site_root.mkdir(parents=True, exist_ok=True)
    malicious_site = Site(
        root=site_root,
        name="myorg-ops-site",
        workspace_root_advisory=None,
        defaults={},
        target_defaults={},
        packs={},
        groups={},
        bindings=[
            Binding(name="..", role="kubeops-copilot", target={"kubeContext": "kind-demo"})
        ],
    )
    monkeypatch.setattr("aoh.cli.load_site", lambda _site_arg: malicious_site)

    workspace_root = tmp_path / "agents"
    workspace_root.mkdir(parents=True, exist_ok=True)

    main(["list", "--site", str(site_root), "--workspace-root", str(workspace_root)])

    captured = capsys.readouterr()
    # The raw-join bug prints the resolved parent of workspace_root (tmp_path
    # itself) in the WORKSPACE column — i.e. the string form of `workspace_root`
    # with a trailing `/..` component collapsed out by str-printing of the Path.
    # Assert the escaped, resolved ancestor path never appears in stdout.
    escaped_path = str((workspace_root / "..").resolve())
    assert escaped_path not in captured.out, (
        f"WORKSPACE column leaked a path outside workspace_root: {captured.out!r}"
    )


# ---------------------------------------------------------------------------
# aoh config
# ---------------------------------------------------------------------------


def test_config_init_writes_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    aoh_home = tmp_path / ".aoh"
    monkeypatch.setenv("AOH_HOME", str(aoh_home))

    exit_code = main(["config", "init"])
    assert exit_code == 0

    doc_text = (aoh_home / "config.yaml").read_text(encoding="utf-8")
    assert "apiVersion: openagentix.io/v1alpha2" in doc_text
    assert "kind: UserConfig" in doc_text


def test_config_set_and_get_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    aoh_home = tmp_path / ".aoh"
    monkeypatch.setenv("AOH_HOME", str(aoh_home))

    assert main(["config", "init"]) == 0
    assert main(["config", "set", "defaults.runtime", "codex"]) == 0

    exit_code = main(["config", "get", "defaults.runtime"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "codex" in captured.out


def test_config_get_unset_key_reports_absence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    aoh_home = tmp_path / ".aoh"
    monkeypatch.setenv("AOH_HOME", str(aoh_home))
    assert main(["config", "init"]) == 0

    exit_code = main(["config", "get", "site"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() in ("", "(unset)", "None") or "unset" in captured.out.lower()


def test_config_set_dotted_key_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    aoh_home = tmp_path / ".aoh"
    monkeypatch.setenv("AOH_HOME", str(aoh_home))
    assert main(["config", "init"]) == 0
    assert main(["config", "set", "site", "/some/site/path"]) == 0

    from aoh.site import load_user_config

    config = load_user_config(aoh_home)
    assert config.site == "/some/site/path"


# ---------------------------------------------------------------------------
# CLI dispatch order — list/config/lock BEFORE pack loading
# ---------------------------------------------------------------------------


def test_list_dispatch_does_not_require_pack_positional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If `list` incorrectly routed through pack-loading dispatch first, this
    # would raise/attempt to treat something as a pack path. It must not.
    monkeypatch.setenv("AOH_HOME", str(tmp_path / ".aoh"))
    exit_code = main(["list"])
    assert exit_code == 1  # no site configured — but a CLEAN error, not a crash

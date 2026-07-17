"""End-to-end integration test for the v0.3 Phase A chain: a git-sourced
site (real `collections/core/kubeops` pack served from a local bare repo),
`aoh lock`, `aoh install --site` fan-out to two runtimes, and convergent
re-install after a lock update (F1 proven at the CLI level).

Fully hermetic: no network, no real cluster. Everything is driven through
`aoh.cli.main([...])` — the real CLI entrypoint — so this is a true e2e,
not a test of internal functions.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.cli import main
from aoh.site import load_site_lock


# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def make_kubeops_bare_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    """Copy the REAL `collections/core/kubeops` pack into a temp work clone
    under the same relative path, commit it, and push to a bare repo's
    `main`. Returns (bare_repo_path, work_clone_path, commit_A_sha)."""
    bare = tmp_path / "kubeops-origin.git"
    _run(["git", "init", "--bare", "-q", str(bare)], cwd=tmp_path)

    work = tmp_path / "_seed-kubeops"
    _run(["git", "init", "-q", str(work)], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "Test"], cwd=work)

    dest = work / "collections" / "core" / "kubeops"
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["cp", "-R", str(PROJECT_ROOT / "collections" / "core" / "kubeops"), str(dest)],
        cwd=tmp_path,
    )

    _run(["git", "add", "-A"], cwd=work)
    _run(["git", "commit", "-q", "-m", "seed real kubeops pack"], cwd=work)
    commit_a = _run(["git", "rev-parse", "HEAD"], cwd=work).stdout.strip()
    _run(["git", "remote", "add", "origin", str(bare)], cwd=work)
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)

    return bare, work, commit_a


def bare_repo_url(bare: Path) -> str:
    return f"file://{bare}"


def add_marker_and_push(work: Path, bare: Path) -> str:
    """Add a marker file to a skill in the already-cloned `work` dir, commit,
    push to main. Returns the new commit sha (commit B)."""
    marker = work / "collections" / "core" / "kubeops" / "skills" / "pod-crashloop-triage" / "MARKER.txt"
    write(marker, "marker content — proves commit B is installed")
    _run(["git", "add", "-A"], cwd=work)
    _run(["git", "commit", "-q", "-m", "add marker to pod-crashloop-triage"], cwd=work)
    commit_b = _run(["git", "rev-parse", "HEAD"], cwd=work).stdout.strip()
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)
    return commit_b


def remove_marker_and_push(work: Path, bare: Path) -> str:
    """Remove the marker file added by `add_marker_and_push`, commit, push
    to main. Returns the new commit sha (commit C)."""
    marker = work / "collections" / "core" / "kubeops" / "skills" / "pod-crashloop-triage" / "MARKER.txt"
    marker.unlink()
    _run(["git", "add", "-A"], cwd=work)
    _run(["git", "commit", "-q", "-m", "remove marker from pod-crashloop-triage"], cwd=work)
    commit_c = _run(["git", "rev-parse", "HEAD"], cwd=work).stdout.strip()
    _run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work)
    return commit_c


def write_site_yaml(site_root: Path, bare: Path, site_name: str = "e2e-site") -> Path:
    path = site_root / "site.yaml"
    write(
        path,
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Site
        metadata:
          name: {site_name}
        spec:
          bindingsDir: bindings/
          packs:
            kubeops:
              repo: {bare_repo_url(bare)}
              subdir: collections/core/kubeops
              ref: main
        """,
    )
    return path


def write_binding(path: Path, name: str, runtime: str, kube_context: str = "kind-e2e-demo") -> Path:
    write(
        path,
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: {name}
        spec:
          role: kubeops-copilot
          runtime: {runtime}
          access: scoped
          target:
            kubeContext: {kube_context}
            namespace: default
        """,
    )
    return path


# ---------------------------------------------------------------------------
# the e2e test
# ---------------------------------------------------------------------------


def test_site_fan_out_e2e_locked_git_sourced_pack_convergent_reinstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    aoh_home = tmp_path / "aoh-home"
    monkeypatch.setenv("AOH_HOME", str(aoh_home))

    # ---- 1. bare repo fixture with the REAL kubeops pack, commit A -------
    bare, work, commit_a = make_kubeops_bare_repo(tmp_path)
    assert len(commit_a) == 40

    # ---- 2. site dir: site.yaml + 2 bindings (claude-code, codex) --------
    site_root = tmp_path / "site"
    write_site_yaml(site_root, bare)
    write_binding(site_root / "bindings" / "claude-binding.yaml", "claude-binding", "claude-code")
    write_binding(site_root / "bindings" / "codex-binding.yaml", "codex-binding", "codex")

    workspace_root = tmp_path / "workspaces"

    # ---- 3. `aoh lock` -> site.lock.yaml, resolvedCommit == A ------------
    exit_code = main(["lock", "--site", str(site_root)])
    assert exit_code == 0
    assert (site_root / "site.lock.yaml").exists()

    lock = load_site_lock(site_root)
    assert lock is not None
    assert lock.packs["kubeops"].resolved_commit == commit_a

    # ---- 4. `aoh install --site` -> both workspaces materialize ----------
    exit_code = main(
        [
            "install",
            "--site",
            str(site_root),
            "--workspace-root",
            str(workspace_root),
        ]
    )
    assert exit_code == 0

    claude_workspace = workspace_root / "claude-binding"
    codex_workspace = workspace_root / "codex-binding"

    claude_manifest_path = claude_workspace / "aoh-manifest.json"
    codex_manifest_path = codex_workspace / "aoh-manifest.json"
    assert claude_manifest_path.exists()
    assert codex_manifest_path.exists()

    claude_manifest = json.loads(claude_manifest_path.read_text(encoding="utf-8"))
    codex_manifest = json.loads(codex_manifest_path.read_text(encoding="utf-8"))
    assert claude_manifest["resolvedCommit"] == commit_a
    assert codex_manifest["resolvedCommit"] == commit_a

    assert (claude_workspace / ".claude" / "settings.json").exists()
    assert (codex_workspace / "AGENTS.md").exists()
    ops_skill_dirs = sorted(
        p.name for p in (codex_workspace / ".agents" / "skills").glob("ops-*") if p.is_dir()
    )
    assert ops_skill_dirs, "codex workspace must have .agents/skills/ops-*/ dirs"

    # ---- 6. site-qualified SA name appears in generated provision.sh -----
    claude_provision = (claude_workspace / "provision.sh").read_text(encoding="utf-8")
    codex_provision = (codex_workspace / "provision.sh").read_text(encoding="utf-8")
    assert "aoh-e2e-site-claude-binding" in claude_provision
    assert "aoh-e2e-site-codex-binding" in codex_provision

    # Materialized marker paths differ per adapter: claude-code copies the
    # skill tree verbatim under `.claude/skills/<skill>/`; codex copies it
    # under the `ops-`-wrapped `.agents/skills/ops-<skill>/`.
    claude_marker_relpath = Path(".claude") / "skills" / "pod-crashloop-triage" / "MARKER.txt"
    codex_marker_relpath = Path(".agents") / "skills" / "ops-pod-crashloop-triage" / "MARKER.txt"

    # ---- 5a. commit a pack change (marker file), push commit B ----------
    commit_b = add_marker_and_push(work, bare)
    assert commit_b != commit_a

    # Re-run install WITHOUT lock update: still resolves to commit A, F1 —
    # site.yaml's movable `main` ref changing upstream must not affect an
    # unlocked re-install.
    exit_code = main(
        [
            "install",
            "--site",
            str(site_root),
            "--workspace-root",
            str(workspace_root),
        ]
    )
    assert exit_code == 0

    claude_manifest = json.loads(claude_manifest_path.read_text(encoding="utf-8"))
    assert claude_manifest["resolvedCommit"] == commit_a
    assert not (claude_workspace / claude_marker_relpath).exists()
    assert not (codex_workspace / codex_marker_relpath).exists()

    # `aoh lock --update` moves the lock to commit B.
    exit_code = main(["lock", "--site", str(site_root), "--update"])
    assert exit_code == 0
    lock = load_site_lock(site_root)
    assert lock is not None
    assert lock.packs["kubeops"].resolved_commit == commit_b

    # Re-install: now resolves to commit B, marker PRESENT, convergent
    # install removes any stale files (none expected to be stale here, but
    # this proves the install actually re-materialized from the new commit).
    exit_code = main(
        [
            "install",
            "--site",
            str(site_root),
            "--workspace-root",
            str(workspace_root),
        ]
    )
    assert exit_code == 0

    claude_manifest = json.loads(claude_manifest_path.read_text(encoding="utf-8"))
    codex_manifest = json.loads(codex_manifest_path.read_text(encoding="utf-8"))
    assert claude_manifest["resolvedCommit"] == commit_b
    assert codex_manifest["resolvedCommit"] == commit_b
    assert (claude_workspace / claude_marker_relpath).exists()
    assert (codex_workspace / codex_marker_relpath).exists()
    assert (claude_workspace / claude_marker_relpath).read_text(encoding="utf-8").strip() == (
        "marker content — proves commit B is installed"
    )

    # ---- convergent removal: commit C removes the marker; after a further
    # lock --update + re-install, the now-stale marker file must be removed
    # from BOTH workspaces (proves convergent install deletes stale owned
    # files, not just adds new ones).
    commit_c = remove_marker_and_push(work, bare)
    assert commit_c != commit_b

    exit_code = main(["lock", "--site", str(site_root), "--update"])
    assert exit_code == 0
    lock = load_site_lock(site_root)
    assert lock is not None
    assert lock.packs["kubeops"].resolved_commit == commit_c

    exit_code = main(
        [
            "install",
            "--site",
            str(site_root),
            "--workspace-root",
            str(workspace_root),
        ]
    )
    assert exit_code == 0

    claude_manifest = json.loads(claude_manifest_path.read_text(encoding="utf-8"))
    codex_manifest = json.loads(codex_manifest_path.read_text(encoding="utf-8"))
    assert claude_manifest["resolvedCommit"] == commit_c
    assert codex_manifest["resolvedCommit"] == commit_c
    assert not (claude_workspace / claude_marker_relpath).exists()
    assert not (codex_workspace / codex_marker_relpath).exists()
    # the skill itself is still intact — only the stray marker was pruned
    assert (claude_workspace / ".claude" / "skills" / "pod-crashloop-triage" / "SKILL.md").exists()
    assert (codex_workspace / ".agents" / "skills" / "ops-pod-crashloop-triage" / "SKILL.md").exists()

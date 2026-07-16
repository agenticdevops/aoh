"""Tests for binding `access: inherit` — credential-free kubeconfig overlay mode.

Covers the shared `_k8s.render_overlay_prepare_script` renderer plus the
per-adapter wiring (hermes, claude-code, codex): inherit mode must produce
`prepare-overlay.sh` instead of `provision.sh`, never touch `--raw`, verify
itself via `kubectl config view --minify`, and self-check its own output for
credential material before finishing. Scoped mode (regression) must be
unaffected.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters._k8s import render_overlay_prepare_script
from aoh.adapters.base import MaterializeRequest
from aoh.adapters.claude_code import ClaudeCodeAdapter
from aoh.adapters.codex import CodexAdapter
from aoh.adapters.hermes import install_hermes_agent
from aoh.pack import load_binding, load_pack


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def write_binding(path: Path, *, access: str | None = None) -> Path:
    access_line = f"\n          access: {access}" if access is not None else ""
    write(
        path,
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: kubeops-sresquad
        spec:
          role: kubeops-copilot
          target:
            kubeContext: kind-sresquad-demo
            namespace: default{access_line}
        """,
    )
    return path


def load_kubeops_binding(tmp_path: Path, *, access: str | None):
    return load_binding(write_binding(tmp_path / "binding.yaml", access=access))


def load_kubeops_pack():
    return load_pack(PROJECT_ROOT / "collections/core/kubeops")


# --- _k8s.render_overlay_prepare_script (shared core) ----------------------


def test_render_overlay_prepare_script_never_uses_raw(tmp_path: Path) -> None:
    binding = load_kubeops_binding(tmp_path, access="inherit")
    script = render_overlay_prepare_script(binding)
    assert "--raw" not in script


def test_render_overlay_prepare_script_resolves_context_via_jsonpath(tmp_path: Path) -> None:
    binding = load_kubeops_binding(tmp_path, access="inherit")
    script = render_overlay_prepare_script(binding)
    assert "kubectl config view" in script
    assert "jsonpath=" in script
    assert "kind-sresquad-demo" in script


def test_render_overlay_prepare_script_contains_minify_verification(tmp_path: Path) -> None:
    binding = load_kubeops_binding(tmp_path, access="inherit")
    script = render_overlay_prepare_script(binding)
    assert "--minify" in script
    assert "exit 1" in script


def test_render_overlay_prepare_script_contains_credential_self_check(tmp_path: Path) -> None:
    binding = load_kubeops_binding(tmp_path, access="inherit")
    script = render_overlay_prepare_script(binding)
    assert "client-key-data" in script
    assert "client-certificate-data" in script
    assert "token:" in script


def test_render_overlay_prepare_script_writes_namespace_and_current_context(tmp_path: Path) -> None:
    binding = load_kubeops_binding(tmp_path, access="inherit")
    script = render_overlay_prepare_script(binding)
    assert "current-context" in script
    assert "default" in script  # namespace


# --- claude-code adapter -----------------------------------------------


def _materialize_claude_code(tmp_path: Path, *, access: str | None) -> Path:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path, access=access)
    adapter = ClaudeCodeAdapter()
    request = MaterializeRequest(
        pack=pack,
        output_dir=tmp_path / "workspace",
        binding=binding,
        role_name="kubeops-copilot",
    )
    adapter.materialize(request)
    return tmp_path / "workspace"


def test_claude_code_inherit_produces_prepare_overlay_not_provision(tmp_path: Path) -> None:
    workspace = _materialize_claude_code(tmp_path, access="inherit")
    assert (workspace / "prepare-overlay.sh").exists()
    assert not (workspace / "provision.sh").exists()
    mode = (workspace / "prepare-overlay.sh").stat().st_mode
    assert mode & 0o111, "prepare-overlay.sh must be executable"


def test_claude_code_scoped_still_produces_provision_regression(tmp_path: Path) -> None:
    workspace = _materialize_claude_code(tmp_path, access=None)
    assert (workspace / "provision.sh").exists()
    assert not (workspace / "prepare-overlay.sh").exists()


def test_claude_code_inherit_launch_sh_has_merge_kubeconfig(tmp_path: Path) -> None:
    workspace = _materialize_claude_code(tmp_path, access="inherit")
    launch = (workspace / "launch.sh").read_text(encoding="utf-8")
    assert 'KUBECONFIG="${DIR}/kubeconfig-overlay:${KUBECONFIG:-$HOME/.kube/config}"' in launch


def test_claude_code_scoped_launch_sh_has_single_path_regression(tmp_path: Path) -> None:
    workspace = _materialize_claude_code(tmp_path, access=None)
    launch = (workspace / "launch.sh").read_text(encoding="utf-8")
    assert 'KUBECONFIG="${DIR}/kubeconfig"' in launch
    assert "kubeconfig-overlay" not in launch


def test_claude_code_inherit_settings_json_env_kubeconfig_is_merge_value(tmp_path: Path) -> None:
    workspace = _materialize_claude_code(tmp_path, access="inherit")
    settings = json.loads((workspace / ".claude" / "settings.json").read_text(encoding="utf-8"))
    overlay_path = str((workspace / "kubeconfig-overlay").resolve())
    assert settings["env"]["KUBECONFIG"] == f"{overlay_path}:${{KUBECONFIG:-$HOME/.kube/config}}"


def test_claude_code_scoped_settings_json_env_kubeconfig_is_single_path_regression(
    tmp_path: Path,
) -> None:
    workspace = _materialize_claude_code(tmp_path, access=None)
    settings = json.loads((workspace / ".claude" / "settings.json").read_text(encoding="utf-8"))
    kubeconfig_path = str((workspace / "kubeconfig").resolve())
    assert settings["env"]["KUBECONFIG"] == kubeconfig_path


def test_claude_code_inherit_claude_md_states_no_hard_boundary(tmp_path: Path) -> None:
    workspace = _materialize_claude_code(tmp_path, access="inherit")
    claude_md = (workspace / "CLAUDE.md").read_text(encoding="utf-8")
    assert "your credentials" in claude_md.lower() or "your own credentials" in claude_md.lower()
    assert "no hard enforcement boundary" in claude_md.lower()


def test_claude_code_inherit_diagnostics_include_inherit_warning(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path, access="inherit")
    adapter = ClaudeCodeAdapter()
    request = MaterializeRequest(
        pack=pack,
        output_dir=tmp_path / "workspace",
        binding=binding,
        role_name="kubeops-copilot",
    )
    result = adapter.materialize(request)
    assert any(
        "access=inherit: no RBAC boundary" in diag for diag in result.diagnostics
    )


# --- codex adapter -------------------------------------------------------


def _materialize_codex(tmp_path: Path, *, access: str | None) -> Path:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path, access=access)
    adapter = CodexAdapter()
    request = MaterializeRequest(
        pack=pack,
        output_dir=tmp_path / "workspace",
        binding=binding,
        role_name="kubeops-copilot",
    )
    adapter.materialize(request)
    return tmp_path / "workspace"


def test_codex_inherit_produces_prepare_overlay_not_provision(tmp_path: Path) -> None:
    workspace = _materialize_codex(tmp_path, access="inherit")
    assert (workspace / "prepare-overlay.sh").exists()
    assert not (workspace / "provision.sh").exists()
    mode = (workspace / "prepare-overlay.sh").stat().st_mode
    assert mode & 0o111, "prepare-overlay.sh must be executable"


def test_codex_scoped_still_produces_provision_regression(tmp_path: Path) -> None:
    workspace = _materialize_codex(tmp_path, access=None)
    assert (workspace / "provision.sh").exists()
    assert not (workspace / "prepare-overlay.sh").exists()


def test_codex_inherit_launch_sh_has_merge_kubeconfig(tmp_path: Path) -> None:
    workspace = _materialize_codex(tmp_path, access="inherit")
    launch = (workspace / "launch.sh").read_text(encoding="utf-8")
    assert 'KUBECONFIG="${DIR}/kubeconfig-overlay:${KUBECONFIG:-$HOME/.kube/config}"' in launch


def test_codex_scoped_launch_sh_has_single_path_regression(tmp_path: Path) -> None:
    workspace = _materialize_codex(tmp_path, access=None)
    launch = (workspace / "launch.sh").read_text(encoding="utf-8")
    assert 'KUBECONFIG="${DIR}/kubeconfig"' in launch
    assert "kubeconfig-overlay" not in launch


def test_codex_inherit_agents_md_states_no_hard_boundary(tmp_path: Path) -> None:
    workspace = _materialize_codex(tmp_path, access="inherit")
    agents_md = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "your credentials" in agents_md.lower() or "your own credentials" in agents_md.lower()
    assert "no hard enforcement boundary" in agents_md.lower()


def test_codex_inherit_diagnostics_include_inherit_warning(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path, access="inherit")
    adapter = CodexAdapter()
    request = MaterializeRequest(
        pack=pack,
        output_dir=tmp_path / "workspace",
        binding=binding,
        role_name="kubeops-copilot",
    )
    result = adapter.materialize(request)
    assert any(
        "access=inherit: no RBAC boundary" in diag for diag in result.diagnostics
    )


# --- hermes adapter --------------------------------------------------------


def _install_hermes(tmp_path: Path, *, access: str | None) -> Path:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path, access=access)
    install_hermes_agent(
        pack,
        tmp_path / "profiles",
        profile_name="kubeops-sresquad",
        provider="openai-codex",
        model="gpt-5.4",
        cwd="/tmp",
        binding=binding,
    )
    return tmp_path / "profiles" / "kubeops-sresquad"


def test_hermes_inherit_produces_prepare_overlay_not_provision(tmp_path: Path) -> None:
    profile = _install_hermes(tmp_path, access="inherit")
    assert (profile / "prepare-overlay.sh").exists()
    assert not (profile / "provision.sh").exists()
    mode = (profile / "prepare-overlay.sh").stat().st_mode
    assert mode & 0o111, "prepare-overlay.sh must be executable"


def test_hermes_scoped_still_produces_provision_regression(tmp_path: Path) -> None:
    profile = _install_hermes(tmp_path, access=None)
    assert (profile / "provision.sh").exists()
    assert not (profile / "prepare-overlay.sh").exists()


def test_hermes_inherit_launch_sh_has_merge_kubeconfig(tmp_path: Path) -> None:
    profile = _install_hermes(tmp_path, access="inherit")
    launch = (profile / "launch.sh").read_text(encoding="utf-8")
    assert "kubeconfig-overlay" in launch
    assert '${KUBECONFIG:-$HOME/.kube/config}' in launch


def test_hermes_scoped_launch_sh_has_single_path_regression(tmp_path: Path) -> None:
    profile = _install_hermes(tmp_path, access=None)
    launch = (profile / "launch.sh").read_text(encoding="utf-8")
    assert "kubeconfig-overlay" not in launch


def test_hermes_inherit_soul_states_no_hard_boundary(tmp_path: Path) -> None:
    profile = _install_hermes(tmp_path, access="inherit")
    soul = (profile / "SOUL.md").read_text(encoding="utf-8")
    assert "your credentials" in soul.lower() or "your own credentials" in soul.lower()
    assert "no hard enforcement boundary" in soul.lower()


def test_hermes_inherit_diagnostics_include_inherit_warning(tmp_path: Path) -> None:
    pack = load_kubeops_pack()
    binding = load_kubeops_binding(tmp_path, access="inherit")
    result = install_hermes_agent(
        pack,
        tmp_path / "profiles",
        profile_name="kubeops-sresquad",
        provider="openai-codex",
        model="gpt-5.4",
        cwd="/tmp",
        binding=binding,
    )
    assert any(
        "access=inherit: no RBAC boundary" in diag for diag in result.diagnostics
    )

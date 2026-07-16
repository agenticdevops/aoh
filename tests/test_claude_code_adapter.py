import json
import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters.base import ADAPTERS, AdapterResult, MaterializeRequest
from aoh.adapters.claude_code import ClaudeCodeAdapter
from aoh.pack import PackError, load_binding, load_pack


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


def materialize(tmp_path: Path, *, access: str | None = None) -> AdapterResult:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")
    binding = load_binding(write_binding(tmp_path / "binding.yaml", access=access))

    adapter = ClaudeCodeAdapter()
    request = MaterializeRequest(
        pack=pack,
        output_dir=tmp_path / "workspace",
        binding=binding,
        role_name="kubeops-copilot",
    )
    return adapter.materialize(request)


def run_hook(hook_path: Path, command: str | None, *, raw_stdin: str | None = None) -> subprocess.CompletedProcess:
    if raw_stdin is not None:
        stdin = raw_stdin
    else:
        stdin = json.dumps({"tool_input": {"command": command}})
    return subprocess.run(
        ["bash", str(hook_path)],
        input=stdin,
        capture_output=True,
        text=True,
    )


# --- registry ---------------------------------------------------------


def test_adapters_registry_contains_claude_code() -> None:
    assert "claude-code" in ADAPTERS
    assert isinstance(ADAPTERS["claude-code"], ClaudeCodeAdapter)
    assert ADAPTERS["claude-code"].name == "claude-code"


def test_importing_only_base_and_package_populates_both_adapters() -> None:
    # Regression guard for T1 carry-forward: ADAPTERS must be populated by
    # package import side-effects alone, not by having previously imported
    # aoh.adapters.hermes / aoh.adapters.claude_code directly in this process.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'src'); "
            "from aoh.adapters.base import ADAPTERS; "
            "print(sorted(ADAPTERS.keys()))",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "'claude-code'" in result.stdout
    assert "'hermes'" in result.stdout


# --- workspace file set -------------------------------------------------


def test_materialize_creates_expected_workspace_file_set(tmp_path: Path) -> None:
    result = materialize(tmp_path)

    workspace = tmp_path / "workspace"
    assert result.runtime == "claude-code"
    assert result.output_dir == workspace

    assert (workspace / ".claude" / "settings.json").exists()
    assert (workspace / ".claude" / "hooks" / "kubectl-guard.sh").exists()
    assert (workspace / ".claude" / "agents" / "kubeops-copilot.md").exists()
    assert (workspace / "CLAUDE.md").exists()
    assert (workspace / "launch.sh").exists()
    assert (workspace / "provision.sh").exists()
    # kubeconfig itself is written by provision.sh at run time, not at
    # materialize time (matches the Hermes adapter's scoped-mode contract).

    for skill in (
        "pod-crashloop-triage",
        "pending-pod-triage",
        "node-notready-triage",
        "k8s-service-health-report",
    ):
        assert (workspace / ".claude" / "skills" / skill / "SKILL.md").exists()
        assert (workspace / ".claude" / "commands" / "ops" / f"{skill}.md").exists()


def test_materialize_inherit_access_raises_not_yet_supported(tmp_path: Path) -> None:
    try:
        materialize(tmp_path, access="inherit")
    except PackError as exc:
        assert "access=inherit not yet supported by claude-code adapter" in str(exc)
    else:
        raise AssertionError("inherit access should raise PackError in claude-code adapter")


# --- settings.json --------------------------------------------------------


def test_settings_json_structure(tmp_path: Path) -> None:
    materialize(tmp_path)
    settings_path = tmp_path / "workspace" / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    workspace = (tmp_path / "workspace").resolve()
    assert settings["env"]["KUBECONFIG"] == str(workspace / "kubeconfig")

    deny = settings["permissions"]["deny"]
    assert "Bash(kubectl delete:*)" in deny
    from aoh.adapters._k8s import KUBECTL_MUTATION_COMMANDS, KUBECTL_READ_COMMANDS

    for verb in KUBECTL_MUTATION_COMMANDS:
        assert f"Bash(kubectl {verb}:*)" in deny
    for helm_verb in ("install", "upgrade", "uninstall", "rollback"):
        assert f"Bash(helm {helm_verb}:*)" in deny

    allow = settings["permissions"]["allow"]
    for cmd in KUBECTL_READ_COMMANDS:
        assert f"Bash(kubectl {cmd}:*)" in allow
    assert "Bash(./.claude/skills/*)" in allow
    assert not any("kubectl config" in entry for entry in allow)

    assert settings["permissions"]["defaultMode"] == "default"

    hooks = settings["hooks"]["PreToolUse"]
    assert hooks[0]["matcher"] == "Bash"
    hook_command = hooks[0]["hooks"][0]["command"]
    assert hook_command == str(workspace / ".claude" / "hooks" / "kubectl-guard.sh")


# --- CLAUDE.md / agents / commands ----------------------------------------


def test_claude_md_states_hard_enforcement_boundary(tmp_path: Path) -> None:
    materialize(tmp_path)
    claude_md = (tmp_path / "workspace" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "hard enforcement boundary" in claude_md.lower()
    assert "kubeops-copilot" in claude_md


def test_agent_file_rendered_per_role(tmp_path: Path) -> None:
    materialize(tmp_path)
    agent_md = (tmp_path / "workspace" / ".claude" / "agents" / "kubeops-copilot.md").read_text(
        encoding="utf-8"
    )
    assert agent_md.startswith("---")
    assert "name: kubeops-copilot" in agent_md
    assert "description:" in agent_md


def test_command_file_per_skill(tmp_path: Path) -> None:
    materialize(tmp_path)
    command_md = (
        tmp_path / "workspace" / ".claude" / "commands" / "ops" / "pod-crashloop-triage.md"
    ).read_text(encoding="utf-8")
    assert "pod-crashloop-triage" in command_md


# --- hook: static properties -----------------------------------------------


def test_hook_script_is_executable(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    mode = hook_path.stat().st_mode
    assert mode & 0o755 == 0o755


# --- hook: behavior (fabricated stdin JSON, real bash) ---------------------


def test_hook_blocks_plain_delete(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "kubectl delete pod x")
    assert result.returncode == 2
    assert result.stderr.strip() != ""


def test_hook_blocks_context_flag_before_verb(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "kubectl --context prod delete pod x")
    assert result.returncode == 2


def test_hook_blocks_absolute_path_kubectl(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "/usr/bin/kubectl delete pod x")
    assert result.returncode == 2


def test_hook_blocks_sh_c_wrapper(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, 'sh -c "kubectl delete pod x"')
    assert result.returncode == 2


def test_hook_blocks_bash_c_wrapper(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "bash -c 'kubectl delete pod x'")
    assert result.returncode == 2


def test_hook_blocks_auth_reconcile(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "kubectl auth reconcile -f rbac.yaml")
    assert result.returncode == 2


def test_hook_blocks_sudo_wrapped_mutation(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "sudo kubectl delete pod x")
    assert result.returncode == 2


def test_hook_blocks_helm_install(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "helm install foo ./chart")
    assert result.returncode == 2


def test_hook_blocks_ambiguous_pipe(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "echo delete | kubectl delete pod x")
    assert result.returncode == 2


def test_hook_blocks_command_substitution(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "echo $(kubectl delete pod x)")
    assert result.returncode == 2


def test_hook_allows_get_pods_all_namespaces(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "kubectl get pods -A")
    assert result.returncode == 0


def test_hook_allows_auth_can_i(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "kubectl auth can-i delete pods")
    assert result.returncode == 0


def test_hook_allows_read_with_context_flag_before_verb(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "kubectl --context prod get pods")
    assert result.returncode == 0


def test_hook_allows_non_kubectl_command(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "ls -la")
    assert result.returncode == 0


def test_hook_exits_2_on_garbage_stdin(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, None, raw_stdin="not json at all {{{")
    assert result.returncode == 2


def test_hook_exits_2_on_empty_command(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, "")
    assert result.returncode == 2


def test_hook_exits_2_on_missing_tool_input(tmp_path: Path) -> None:
    materialize(tmp_path)
    hook_path = tmp_path / "workspace" / ".claude" / "hooks" / "kubectl-guard.sh"
    result = run_hook(hook_path, None, raw_stdin=json.dumps({"foo": "bar"}))
    assert result.returncode == 2

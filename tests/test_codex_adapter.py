"""Tests for the Codex runtime adapter.

Live `codex execpolicy check` verification (codex-cli 0.144.5, binary at
/Users/gshah/.nvm/versions/node/v22.22.2/bin/codex), scratch pre-check run
independently against a hand-written rules file BEFORE the renderer was
finalized:

    $ cat scratch.rules
    prefix_rule(pattern=["kubectl", "delete"], decision="forbidden")
    prefix_rule(pattern=["kubectl", "auth", "can-i"], decision="allow")
    prefix_rule(pattern=["kubectl", "get"], decision="allow")

    $ codex execpolicy check --rules scratch.rules -- kubectl delete pod x
    {"matchedRules":[{"prefixRuleMatch":{"matchedPrefix":["kubectl","delete"],"decision":"forbidden"}}],"decision":"forbidden"}

    $ codex execpolicy check --rules scratch.rules -- kubectl get pods
    {"matchedRules":[{"prefixRuleMatch":{"matchedPrefix":["kubectl","get"],"decision":"allow"}}],"decision":"allow"}

    $ codex execpolicy check --rules scratch.rules -- kubectl auth can-i delete pods
    {"matchedRules":[{"prefixRuleMatch":{"matchedPrefix":["kubectl","auth","can-i"],"decision":"allow"}}],"decision":"allow"}

    $ codex execpolicy check --rules scratch.rules -- kubectl --context prod delete pod x
    {"matchedRules":[]}

    $ codex execpolicy check --rules scratch.rules -- /usr/bin/kubectl delete pod x
    {"matchedRules":[]}

    $ codex execpolicy check --rules scratch.rules -- sh -c "kubectl delete pod x"
    {"matchedRules":[]}

CRITICAL GOTCHA (confirmed): `codex execpolicy check` always exits 0
regardless of decision. The decision must be read from the parsed JSON
`"decision"` field, never from `returncode`.

The live integration tests below re-run this same check against the
adapter's OWN generated rules file (not the scratch file above) and record
their real output in-line as they run; see
`test_live_execpolicy_check_against_generated_rules` for the exact
invocation used.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters._k8s import KUBECTL_MUTATION_COMMANDS, KUBECTL_READ_COMMANDS
from aoh.adapters.base import ADAPTERS, AdapterResult, MaterializeRequest
from aoh.adapters.codex import CodexAdapter
from aoh.pack import PackError, load_binding, load_pack


_HELM_MUTATION_COMMANDS = ("install", "upgrade", "uninstall", "rollback")

_SKILLS = (
    "pod-crashloop-triage",
    "pending-pod-triage",
    "node-notready-triage",
    "k8s-service-health-report",
)


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


def materialize(
    tmp_path: Path, *, access: str | None = None, model_hint: str | None = None
) -> AdapterResult:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")
    binding = load_binding(write_binding(tmp_path / "binding.yaml", access=access))

    adapter = CodexAdapter()
    request = MaterializeRequest(
        pack=pack,
        output_dir=tmp_path / "workspace",
        binding=binding,
        role_name="kubeops-copilot",
        model_hint=model_hint,
    )
    return adapter.materialize(request)


# --- registry ---------------------------------------------------------


def test_adapters_registry_contains_codex() -> None:
    assert "codex" in ADAPTERS
    assert isinstance(ADAPTERS["codex"], CodexAdapter)
    assert ADAPTERS["codex"].name == "codex"


def test_importing_only_base_and_package_populates_all_three_adapters() -> None:
    # Regression guard: ADAPTERS must be populated by package import
    # side-effects alone, not by having previously imported
    # aoh.adapters.hermes / claude_code / codex directly in this process.
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
    assert "'codex'" in result.stdout
    assert "'hermes'" in result.stdout


# --- workspace file set -------------------------------------------------


def test_materialize_creates_expected_workspace_file_set(tmp_path: Path) -> None:
    result = materialize(tmp_path)

    workspace = tmp_path / "workspace"
    assert result.runtime == "codex"
    assert result.output_dir == workspace

    assert (workspace / "AGENTS.md").exists()
    assert (workspace / ".codex" / "config.toml").exists()
    assert (workspace / ".codex" / "rules" / "kubectl-readonly.rules").exists()
    assert (workspace / "launch.sh").exists()
    assert (workspace / "provision.sh").exists()
    # kubeconfig itself is written by provision.sh at run time, not at
    # materialize time (matches the claude-code / hermes adapter contract).
    assert not (workspace / "kubeconfig").exists()

    for skill in _SKILLS:
        skill_dir = workspace / ".agents" / "skills" / f"ops-{skill}"
        skill_md = skill_dir / "SKILL.md"
        assert skill_md.exists()
        frontmatter_text = skill_md.read_text(encoding="utf-8")
        assert f"name: ops-{skill}" in frontmatter_text
        assert f"name: {skill}\n" not in frontmatter_text


def test_no_codex_prompts_directory_anywhere(tmp_path: Path) -> None:
    materialize(tmp_path)
    workspace = tmp_path / "workspace"
    matches = list(workspace.rglob("prompts"))
    assert matches == [] or not any(m.is_dir() and m.name == "prompts" for m in matches)
    assert not (workspace / ".codex" / "prompts").exists()


def test_materialize_inherit_access_produces_overlay_workspace(tmp_path: Path) -> None:
    # access=inherit is supported (Task 5): prepare-overlay.sh instead of
    # provision.sh. Full coverage lives in tests/test_inherit_mode.py; this
    # regression guard just confirms materialize() no longer raises here.
    result = materialize(tmp_path, access="inherit")
    workspace = tmp_path / "workspace"
    assert (workspace / "prepare-overlay.sh").exists()
    assert not (workspace / "provision.sh").exists()
    assert result.runtime == "codex"


# --- skill frontmatter rewrite -------------------------------------------


def test_skill_frontmatter_name_rewritten_dir_and_content_match(tmp_path: Path) -> None:
    materialize(tmp_path)
    workspace = tmp_path / "workspace"
    for skill in _SKILLS:
        skill_dir = workspace / ".agents" / "skills" / f"ops-{skill}"
        skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert skill_md.startswith("---")
        parts = skill_md.split("---", 2)
        frontmatter = parts[1]
        name_lines = [
            line for line in frontmatter.splitlines() if line.strip().startswith("name:")
        ]
        assert len(name_lines) == 1
        assert name_lines[0].strip() == f"name: ops-{skill}"
        # description preserved, not clobbered
        assert "description:" in frontmatter


def test_rewritten_skill_md_preserves_frontmatter_structure(tmp_path: Path) -> None:
    # Regression: the rewrite must change ONLY the frontmatter `name:` line,
    # byte-for-byte otherwise. A prior bug dropped the trailing newline of
    # the frontmatter segment, gluing the closing `---` delimiter onto the
    # last frontmatter line (e.g. `description: ...---`), which is malformed
    # frontmatter and corrupts the description value.
    materialize(tmp_path)
    workspace = tmp_path / "workspace"
    for skill in _SKILLS:
        source_text = (
            PROJECT_ROOT / "collections/core/kubeops/skills" / skill / "SKILL.md"
        ).read_text(encoding="utf-8")
        rewritten_text = (
            workspace / ".agents" / "skills" / f"ops-{skill}" / "SKILL.md"
        ).read_text(encoding="utf-8")

        expected = source_text.replace(f"name: {skill}\n", f"name: ops-{skill}\n", 1)
        assert rewritten_text == expected

        # Belt and braces: the closing delimiter must stand on its own line,
        # and no frontmatter line may have `---` glued onto its end.
        closing = rewritten_text.index("\n---\n", 3)
        frontmatter = rewritten_text[4:closing]
        assert not any(line.endswith("---") for line in frontmatter.splitlines())


def test_skill_scripts_copied_alongside(tmp_path: Path) -> None:
    materialize(tmp_path)
    workspace = tmp_path / "workspace"
    for skill in _SKILLS:
        scripts_dir = workspace / ".agents" / "skills" / f"ops-{skill}" / "scripts"
        source_scripts = PROJECT_ROOT / "collections/core/kubeops/skills" / skill / "scripts"
        if source_scripts.exists():
            assert scripts_dir.exists()
            assert sorted(p.name for p in scripts_dir.iterdir()) == sorted(
                p.name for p in source_scripts.iterdir()
            )


# --- AGENTS.md -------------------------------------------------------------


def test_agents_md_content(tmp_path: Path) -> None:
    materialize(tmp_path)
    agents_md = (tmp_path / "workspace" / "AGENTS.md").read_text(encoding="utf-8")
    assert "kubeops-copilot" in agents_md
    for skill in _SKILLS:
        assert f"$ops-{skill}" in agents_md
    assert "read-only" in agents_md.lower()
    assert (
        "cluster rbac is the enforcement boundary; the rules file is best-effort"
        in agents_md.lower()
    )


# --- config.toml -------------------------------------------------------------


def test_config_toml_default_model(tmp_path: Path) -> None:
    materialize(tmp_path)
    config_path = tmp_path / "workspace" / ".codex" / "config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert config["model"] == "gpt-5.4"
    assert config["model_reasoning_effort"] == "medium"
    assert config["approval_policy"] == "on-request"
    assert config["sandbox_mode"] == "workspace-write"
    assert config["sandbox_workspace_write"]["network_access"] is True


def test_config_toml_model_hint_override(tmp_path: Path) -> None:
    materialize(tmp_path, model_hint="gpt-9000")
    config_path = tmp_path / "workspace" / ".codex" / "config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert config["model"] == "gpt-9000"


# --- rules file -------------------------------------------------------------


def test_rules_file_header_documents_gaps(tmp_path: Path) -> None:
    materialize(tmp_path)
    rules_text = (
        tmp_path / "workspace" / ".codex" / "rules" / "kubectl-readonly.rules"
    ).read_text(encoding="utf-8")

    assert rules_text.startswith("#")
    lowered = rules_text.lower()
    assert "--context" in rules_text
    assert "/usr/bin/kubectl" in rules_text
    assert "sh -c" in rules_text
    assert "rbac" in lowered


def test_rules_file_forbidden_entries_cover_mutation_verbs(tmp_path: Path) -> None:
    materialize(tmp_path)
    rules_text = (
        tmp_path / "workspace" / ".codex" / "rules" / "kubectl-readonly.rules"
    ).read_text(encoding="utf-8")

    for verb in KUBECTL_MUTATION_COMMANDS:
        assert f'prefix_rule(pattern=["kubectl", "{verb}"], decision="forbidden")' in rules_text

    for helm_verb in _HELM_MUTATION_COMMANDS:
        assert f'prefix_rule(pattern=["helm", "{helm_verb}"], decision="forbidden")' in rules_text


def test_rules_file_allow_entries_cover_read_verbs(tmp_path: Path) -> None:
    materialize(tmp_path)
    rules_text = (
        tmp_path / "workspace" / ".codex" / "rules" / "kubectl-readonly.rules"
    ).read_text(encoding="utf-8")

    for verb in KUBECTL_READ_COMMANDS:
        tokens = verb.split()
        pattern = ", ".join(f'"{t}"' for t in ["kubectl", *tokens])
        assert f'prefix_rule(pattern=[{pattern}], decision="allow")' in rules_text


# --- diagnostics -------------------------------------------------------------


def test_diagnostics_non_empty_and_mentions_best_effort(tmp_path: Path) -> None:
    result = materialize(tmp_path)
    assert result.diagnostics != []
    joined = " ".join(result.diagnostics).lower()
    assert "best-effort" in joined
    assert "rbac is the enforcement boundary" in joined
    assert "--context" in " ".join(result.diagnostics)
    assert "absolute path" in joined
    assert "shell wrapper" in joined


# --- launch.sh -------------------------------------------------------------


def test_launch_script_exports_kubeconfig_and_execs_codex(tmp_path: Path) -> None:
    materialize(tmp_path)
    launch_sh = (tmp_path / "workspace" / "launch.sh").read_text(encoding="utf-8")
    assert launch_sh.startswith("#!/usr/bin/env bash")
    assert "KUBECONFIG" in launch_sh
    assert 'exec codex "$@"' in launch_sh

    mode = (tmp_path / "workspace" / "launch.sh").stat().st_mode
    assert mode & 0o755 == 0o755


def test_provision_script_written_and_executable(tmp_path: Path) -> None:
    materialize(tmp_path)
    provision_path = tmp_path / "workspace" / "provision.sh"
    assert provision_path.exists()
    mode = provision_path.stat().st_mode
    assert mode & 0o755 == 0o755
    text = provision_path.read_text(encoding="utf-8")
    assert "kubeops-sresquad" in text


# --- live execpolicy integration -------------------------------------------


def test_live_execpolicy_check_against_generated_rules(tmp_path: Path) -> None:
    if shutil.which("codex") is None:
        print("codex CLI not found, skipping live execpolicy check")
        return

    materialize(tmp_path)
    rules_path = tmp_path / "workspace" / ".codex" / "rules" / "kubectl-readonly.rules"

    forbidden = subprocess.run(
        [
            "codex",
            "execpolicy",
            "check",
            "--rules",
            str(rules_path),
            "--",
            "kubectl",
            "delete",
            "pod",
            "x",
        ],
        capture_output=True,
        text=True,
    )
    # codex execpolicy check always exits 0 regardless of decision — parse
    # the JSON "decision" field, never the returncode.
    forbidden_payload = json.loads(forbidden.stdout)
    assert forbidden_payload["decision"] == "forbidden"

    allowed = subprocess.run(
        [
            "codex",
            "execpolicy",
            "check",
            "--rules",
            str(rules_path),
            "--",
            "kubectl",
            "get",
            "pods",
        ],
        capture_output=True,
        text=True,
    )
    allowed_payload = json.loads(allowed.stdout)
    assert allowed_payload["decision"] == "allow"

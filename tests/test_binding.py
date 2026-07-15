from pathlib import Path
import sys
import textwrap


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters.hermes import install_hermes_agent
from aoh.pack import PackError, load_binding, load_pack


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def write_binding(path: Path, **overrides) -> Path:
    api_version = overrides.get("api_version", "openagentix.io/v1alpha2")
    kind = overrides.get("kind", "Binding")
    write(
        path,
        f"""
        apiVersion: {api_version}
        kind: {kind}
        metadata:
          name: kubeops-sresquad
        spec:
          role: kubeops-copilot
          target:
            kubeContext: kind-sresquad-demo
            namespace: default
        """,
    )
    return path


def test_load_binding_happy_path(tmp_path: Path) -> None:
    binding = load_binding(write_binding(tmp_path / "binding.yaml"))

    assert binding.name == "kubeops-sresquad"
    assert binding.role == "kubeops-copilot"
    assert binding.target == {"kubeContext": "kind-sresquad-demo", "namespace": "default"}


def test_load_binding_rejects_wrong_kind(tmp_path: Path) -> None:
    path = write_binding(tmp_path / "binding.yaml", kind="Role")

    try:
        load_binding(path)
    except PackError as exc:
        assert "kind must be Binding" in str(exc)
    else:
        raise AssertionError("load_binding should reject wrong kind")


def test_load_binding_requires_role(tmp_path: Path) -> None:
    path = tmp_path / "binding.yaml"
    write(
        path,
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: kubeops-sresquad
        spec:
          target:
            kubeContext: kind-sresquad-demo
        """,
    )

    try:
        load_binding(path)
    except PackError as exc:
        assert "Binding `kubeops-sresquad` spec.role is required" in str(exc)
    else:
        raise AssertionError("load_binding should require spec.role")


def test_load_binding_requires_target_mapping(tmp_path: Path) -> None:
    path = tmp_path / "binding.yaml"
    write(
        path,
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: kubeops-sresquad
        spec:
          role: kubeops-copilot
        """,
    )

    try:
        load_binding(path)
    except PackError as exc:
        assert "Binding `kubeops-sresquad` spec.target must be a mapping" in str(exc)
    else:
        raise AssertionError("load_binding should require spec.target mapping")


def test_load_binding_rejects_old_api_version(tmp_path: Path) -> None:
    old_api = "openagentix.io/v1alpha" + "1"
    path = write_binding(tmp_path / "binding.yaml", api_version=old_api)

    try:
        load_binding(path)
    except PackError as exc:
        assert "apiVersion must be openagentix.io/v1alpha2" in str(exc)
    else:
        raise AssertionError("load_binding should reject non-v1alpha2 apiVersion")


def test_install_hermes_agent_with_binding_materializes_rbac_artifacts(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")
    binding = load_binding(write_binding(tmp_path / "binding.yaml"))

    install_hermes_agent(
        pack,
        tmp_path / "profiles",
        profile_name="kubeops-sresquad",
        provider="openai-codex",
        model="gpt-5.4",
        cwd="/tmp",
        binding=binding,
    )

    profile = tmp_path / "profiles/kubeops-sresquad"
    provision = profile / "provision.sh"
    launch = profile.joinpath("launch.sh").read_text(encoding="utf-8")
    soul = profile.joinpath("SOUL.md").read_text(encoding="utf-8")
    manifest = profile.joinpath("aoh-agent.json").read_text(encoding="utf-8")

    assert provision.exists()
    provision_text = provision.read_text(encoding="utf-8")
    assert 'CONTEXT="kind-sresquad-demo"' in provision_text
    assert 'SA_NAME="aoh-kubeops-sresquad"' in provision_text
    assert "aoh-readonly" in provision_text
    assert '"get", "list", "watch"' in provision_text
    assert provision.stat().st_mode & 0o111, "provision.sh must be executable"

    assert 'export KUBECONFIG="$(cd "$(dirname "$0")" && pwd)/kubeconfig"' in launch

    assert "## Binding" in soul
    assert "kind-sresquad-demo" in soul
    assert "read-only" in soul

    assert '"binding"' in manifest
    assert "kind-sresquad-demo" in manifest


def test_install_binding_role_defaults_and_missing_role_rejected(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")
    path = tmp_path / "binding.yaml"
    write(
        path,
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: kubeops-sresquad
        spec:
          role: nonexistent-role
          target:
            kubeContext: kind-sresquad-demo
        """,
    )
    binding = load_binding(path)

    try:
        install_hermes_agent(
            pack,
            tmp_path / "profiles",
            profile_name="kubeops-sresquad",
            provider="openai-codex",
            model="gpt-5.4",
            cwd="/tmp",
            binding=binding,
        )
    except PackError as exc:
        assert "Binding `kubeops-sresquad` references missing role `nonexistent-role`" in str(exc)
    else:
        raise AssertionError("install should reject binding to missing role")


def test_install_binding_requires_kube_context(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")
    path = tmp_path / "binding.yaml"
    write(
        path,
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: kubeops-sresquad
        spec:
          role: kubeops-copilot
          target:
            namespace: default
        """,
    )
    binding = load_binding(path)

    try:
        install_hermes_agent(
            pack,
            tmp_path / "profiles",
            profile_name="kubeops-sresquad",
            provider="openai-codex",
            model="gpt-5.4",
            cwd="/tmp",
            binding=binding,
        )
    except PackError as exc:
        assert "Binding `kubeops-sresquad` target.kubeContext is required" in str(exc)
    else:
        raise AssertionError("install should require target.kubeContext")

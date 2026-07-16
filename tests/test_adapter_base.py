from pathlib import Path
import sys
import textwrap


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.adapters.base import AdapterResult, ADAPTERS, MaterializeRequest, RuntimeAdapter
from aoh.adapters.hermes import HermesAdapter, install_hermes_agent
from aoh.pack import PackError, load_binding, load_pack


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def write_binding(path: Path, **overrides) -> Path:
    api_version = overrides.get("api_version", "openagentix.io/v1alpha2")
    kind = overrides.get("kind", "Binding")
    access = overrides.get("access")
    access_line = f"\n          access: {access}" if access is not None else ""
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
            namespace: default{access_line}
        """,
    )
    return path


def test_adapters_registry_contains_hermes() -> None:
    assert "hermes" in ADAPTERS
    assert isinstance(ADAPTERS["hermes"], HermesAdapter)
    assert ADAPTERS["hermes"].name == "hermes"


def test_hermes_adapter_materialize_matches_install_hermes_agent(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")
    binding = load_binding(write_binding(tmp_path / "binding.yaml"))

    adapter = HermesAdapter()
    request = MaterializeRequest(
        pack=pack,
        output_dir=tmp_path / "profiles",
        binding=binding,
        profile="kubeops-sresquad",
        options={"provider": "openai-codex"},
        model_hint="gpt-5.4",
        workdir="/tmp",
    )
    result = adapter.materialize(request)

    assert isinstance(result, AdapterResult)
    assert result.runtime == "hermes"
    assert result.diagnostics == []

    profile = tmp_path / "profiles" / "kubeops-sresquad"
    assert (profile / "config.yaml").exists()
    assert (profile / "SOUL.md").exists()
    assert (profile / "launch.sh").exists()
    assert (profile / "provision.sh").exists()


def test_provision_script_uses_allowlist_not_wildcard(tmp_path: Path) -> None:
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

    provision_text = (tmp_path / "profiles/kubeops-sresquad/provision.sh").read_text(
        encoding="utf-8"
    )
    assert 'resources: ["nodes"' in provision_text
    assert 'resources: ["*"]' not in provision_text
    assert "secrets" not in provision_text


def test_binding_access_defaults_to_scoped(tmp_path: Path) -> None:
    binding = load_binding(write_binding(tmp_path / "binding.yaml"))
    assert binding.access == "scoped"


def test_binding_access_inherit_loads(tmp_path: Path) -> None:
    binding = load_binding(write_binding(tmp_path / "binding.yaml", access="inherit"))
    assert binding.access == "inherit"


def test_binding_access_bogus_rejected(tmp_path: Path) -> None:
    path = write_binding(tmp_path / "binding.yaml", access="bogus")

    try:
        load_binding(path)
    except PackError as exc:
        assert "Binding `kubeops-sresquad` spec.access must be scoped or inherit" in str(exc)
    else:
        raise AssertionError("load_binding should reject unknown access mode")


def test_eks_style_context_accepted(tmp_path: Path) -> None:
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
            kubeContext: arn:aws:eks:us-east-1:123:cluster/x
            namespace: default
        """,
    )
    binding = load_binding(path)

    result = install_hermes_agent(
        pack,
        tmp_path / "profiles",
        profile_name="kubeops-sresquad",
        provider="openai-codex",
        model="gpt-5.4",
        cwd="/tmp",
        binding=binding,
    )
    assert result.output_dir.exists()


def test_bad_sa_name_rejected(tmp_path: Path) -> None:
    pack = load_pack(PROJECT_ROOT / "collections/core/kubeops")
    path = tmp_path / "binding.yaml"
    write(
        path,
        """
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: Bad_Name
        spec:
          role: kubeops-copilot
          target:
            kubeContext: kind-sresquad-demo
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
        assert "must be a DNS-1123 label" in str(exc)
    else:
        raise AssertionError("install should reject non-DNS-1123 binding name")

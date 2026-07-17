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

    # materialize() is exact-dir: it writes into EXACTLY request.output_dir,
    # no extra `<output_dir>/<profile>/` nesting (v0.3 A3 / F9). The legacy
    # `install_hermes_agent` function retains its own nesting behavior
    # unchanged — see test_legacy_install_hermes_agent_still_nests_profile_dir
    # in test_adapter_contract.py.
    adapter = HermesAdapter()
    profile = tmp_path / "profiles" / "kubeops-sresquad"
    request = MaterializeRequest(
        pack=pack,
        output_dir=profile,
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
    assert result.output_dir == profile

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


# Task 5: site-qualified RBAC naming tests
def test_site_qualified_sa_name_renders_correctly(tmp_path: Path) -> None:
    """Site-qualified mode: SA name is aoh-<site_name>-<binding.name>."""
    from aoh.adapters._k8s import render_provision_script

    binding = load_binding(write_binding(tmp_path / "binding.yaml"))
    script = render_provision_script(binding, site_name="sresquad")

    # Both ServiceAccount and ClusterRoleBinding should use the site-qualified name.
    # SA_NAME is set to the site-qualified name.
    assert 'SA_NAME=aoh-sresquad-kubeops-sresquad' in script
    # ClusterRoleBinding uses ${{SA_NAME}} variable, so the literal name won't appear,
    # but we can verify the variable is used and the SA is referenced.
    assert 'name: aoh-readonly-${SA_NAME}' in script
    assert 'name: ${SA_NAME}' in script  # in subjects section


def test_legacy_sa_name_renders_correctly(tmp_path: Path) -> None:
    """Legacy mode (site_name=None): SA name is aoh-<binding.name>."""
    from aoh.adapters._k8s import render_provision_script

    binding = load_binding(write_binding(tmp_path / "binding.yaml"))
    script = render_provision_script(binding, site_name=None)

    # Legacy SA name unchanged.
    assert 'SA_NAME=aoh-kubeops-sresquad' in script
    # ClusterRoleBinding uses ${SA_NAME} variable for legacy name as well.
    assert 'name: aoh-readonly-${SA_NAME}' in script


def test_legacy_sa_name_renders_by_default(tmp_path: Path) -> None:
    """Legacy mode is the default when site_name is not specified."""
    from aoh.adapters._k8s import render_provision_script

    binding = load_binding(write_binding(tmp_path / "binding.yaml"))
    script = render_provision_script(binding)

    # Default behavior is legacy.
    assert 'SA_NAME=aoh-kubeops-sresquad' in script


def test_site_qualified_name_at_62_chars_valid(tmp_path: Path) -> None:
    """Boundary test: final SA name of exactly 62 chars should be valid."""
    from aoh.adapters._k8s import render_provision_script

    # Construct site + binding names to get exactly 62 chars in rendered name.
    # Format: aoh-<site>-<binding> = 4 + len(site) + 1 + len(binding)
    # 62 = 4 + len(site) + 1 + len(binding)
    # len(site) + len(binding) = 57
    # Use site="ss" (2 chars) and binding="b" * 55 = 57
    site_name = "ss"
    path = tmp_path / "binding.yaml"
    write(
        path,
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: {"b" * 55}
        spec:
          role: kubeops-copilot
          target:
            kubeContext: kind-sresquad-demo
            namespace: default
        """,
    )
    binding = load_binding(path)
    script = render_provision_script(binding, site_name=site_name)

    # Should render without error; name should be exactly 62 chars.
    rendered_name = f"aoh-{site_name}-{binding.name}"
    assert len(rendered_name) == 62
    assert f'SA_NAME={rendered_name}' in script


def test_site_qualified_name_at_63_chars_valid(tmp_path: Path) -> None:
    """Boundary test: final SA name of exactly 63 chars should be valid."""
    from aoh.adapters._k8s import render_provision_script

    # 63 = 4 + len(site) + 1 + len(binding)
    # len(site) + len(binding) = 58
    site_name = "sss"
    path = tmp_path / "binding.yaml"
    write(
        path,
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: {"b" * 55}
        spec:
          role: kubeops-copilot
          target:
            kubeContext: kind-sresquad-demo
            namespace: default
        """,
    )
    binding = load_binding(path)
    script = render_provision_script(binding, site_name=site_name)

    # Should render without error; name should be exactly 63 chars.
    rendered_name = f"aoh-{site_name}-{binding.name}"
    assert len(rendered_name) == 63
    assert f'SA_NAME={rendered_name}' in script


def test_site_qualified_name_at_64_chars_rejected(tmp_path: Path) -> None:
    """Boundary test: final SA name of 64 chars should be rejected."""
    from aoh.adapters._k8s import render_provision_script

    # 64 = 4 + len(site) + 1 + len(binding)
    # len(site) + len(binding) = 59
    site_name = "ssss"
    path = tmp_path / "binding.yaml"
    write(
        path,
        f"""
        apiVersion: openagentix.io/v1alpha2
        kind: Binding
        metadata:
          name: {"b" * 55}
        spec:
          role: kubeops-copilot
          target:
            kubeContext: kind-sresquad-demo
            namespace: default
        """,
    )
    binding = load_binding(path)

    try:
        render_provision_script(binding, site_name=site_name)
    except PackError as exc:
        # Should be rejected either because it exceeds 63 chars or fails DNS-1123 regex.
        assert "DNS-1123" in str(exc) or "exceeds" in str(exc).lower()
    else:
        raise AssertionError("Should reject SA name longer than 63 chars")


def test_invalid_site_name_rejected(tmp_path: Path) -> None:
    """Invalid site_name (uppercase) should be rejected via safe_segment."""
    from aoh.adapters._k8s import render_provision_script

    binding = load_binding(write_binding(tmp_path / "binding.yaml"))

    try:
        render_provision_script(binding, site_name="MyCluster")
    except PackError as exc:
        assert "site_name" in str(exc) or "MyCluster" in str(exc)
    else:
        raise AssertionError("Should reject uppercase site_name")


def test_both_sa_and_crb_use_site_qualified_name(tmp_path: Path) -> None:
    """Both ServiceAccount and ClusterRoleBinding names should use site-qualified form."""
    from aoh.adapters._k8s import render_provision_script

    binding = load_binding(write_binding(tmp_path / "binding.yaml"))
    script = render_provision_script(binding, site_name="mysite")

    # Both should use the site-qualified name via SA_NAME variable.
    sa_name = "aoh-mysite-kubeops-sresquad"

    assert f"SA_NAME={sa_name}" in script
    assert f"kind: ClusterRoleBinding" in script
    # ClusterRoleBinding uses ${SA_NAME} variable which references the site-qualified name.
    assert "name: aoh-readonly-${SA_NAME}" in script
    # The ServiceAccount name should be referenced in the subjects section via variable.
    assert "name: ${SA_NAME}" in script

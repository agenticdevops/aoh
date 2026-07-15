from pathlib import Path
import sys
import textwrap


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.pack import PackError, load_binding


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

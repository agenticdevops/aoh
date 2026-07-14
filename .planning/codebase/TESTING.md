# Testing Patterns

**Analysis Date:** 2026-07-14

## Test Framework

**Runner:**
- pytest 8.0+ (specified in `pyproject.toml`)
- Config: `pyproject.toml` with minimal settings: `testpaths = ["tests"]`

**Assertion Library:**
- Built-in `assert` statements (pytest's assertion rewriting)
- No explicit assertion library like `pytest-assert-rewrite` needed

**Run Commands:**
```bash
uv run pytest -q              # Run all tests quietly
uv run pytest                 # Run all tests with verbose output
uv run pytest tests/test_cli.py  # Run single test file
uv run pytest -v              # Run with detailed output
```

## Test File Organization

**Location:**
- Co-located in `tests/` directory at repo root: `tests/test_*.py`
- Separate from source code: `src/aoh/` vs `tests/`
- Not co-located with source modules

**Naming:**
- `test_*.py` pattern for test modules: `test_cli.py`, `test_pack_validation.py`
- `test_*()` pattern for test functions: `test_init_pack_creates_valid_starter_pack()`
- Test names are descriptive of behavior, not just "test_x"

**Structure:**
```
tests/
├── test_cli.py                 # CLI entry point tests
├── test_core_collection.py     # Real pack artifact tests
├── test_hermes_agent.py        # Hermes agent profile generation
├── test_hermes_install.py      # Hermes pack installation
├── test_pack_validation.py     # Pack validation and adapter generation
├── test_role_mapping.py        # Agent role loading and scoping
└── test_team_mapping.py        # Team loading and multi-role installation
```

## Test Structure

**Suite Organization:**
Tests use pytest's function-based approach with explicit fixture creation via helper functions:

```python
from pathlib import Path
import sys

# Setup: add src to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Imports
from aoh.cli import main
from aoh.pack import load_pack, validate_pack

# Test function
def test_init_pack_creates_valid_starter_pack(tmp_path: Path) -> None:
    pack_dir = tmp_path / "packs" / "postgres-health-check"
    
    exit_code = main([
        "init-pack",
        "postgres-health-check",
        "--output", str(pack_dir),
        "--description", "Check PostgreSQL health using read-only diagnostics.",
    ])
    
    assert exit_code == 0
    assert (pack_dir / "AOH.yaml").exists()
    assert (pack_dir / "skills/postgres-health-check/SKILL.md").exists()
    
    pack = load_pack(pack_dir)
    validate_pack(pack)
    
    assert pack.name == "postgres-health-check"
    assert pack.skills == ["postgres-health-check"]
```

**Patterns:**
- Use pytest's built-in `tmp_path` fixture for temporary directories
- Test one behavior per function (single assertion focus)
- Arrange → Act → Assert structure
- Helper functions (`write()`) for shared test data setup
- No `setUp()`/`tearDown()` methods; pytest fixtures and functions suffice

## Mocking

**Framework:** None explicitly detected; tests use real filesystem operations

**Patterns:**
Tests create real temporary packs using helper functions:

```python
def write(path: Path, content: str) -> None:
    """Helper to write test YAML fixtures."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")

def create_docker_cleanup_pack(root: Path) -> Path:
    """Factory function to create a complete valid pack in tmp_path."""
    pack = root / "docker-disk-cleanup"
    write(pack / "AOH.yaml", """...""")
    write(pack / "skills/docker-disk-cleanup/SKILL.md", """...""")
    write(pack / "workflows/docker-disk-cleanup.yaml", """...""")
    # ... more files ...
    return pack
```

**What to Mock:**
- Nothing is mocked; tests use real filesystem via `tmp_path`
- No external services mocked (no network calls to test)
- YAML files written and read for real

**What NOT to Mock:**
- File I/O (real operations used instead)
- YAML parsing (actual `yaml.safe_load()` tested)
- Path operations (real `Path` objects, not mocked)

## Fixtures and Factories

**Test Data:**
Helper functions create complete, valid pack structures:

```python
# From test_pack_validation.py
def create_docker_cleanup_pack(root: Path) -> Path:
    """Factory for a complete valid pack with all required artifacts."""
    pack = root / "docker-disk-cleanup"
    write(pack / "AOH.yaml", """
        apiVersion: openagentix.io/v1alpha1
        kind: Pack
        metadata:
          name: docker-disk-cleanup
          displayName: Docker Disk Cleanup
          description: Diagnose Docker disk usage...
    """)
    # ... skill, workflow, agent, model, runtime requirement, eval files ...
    return pack

# From test_role_mapping.py
def create_multi_role_pack(root: Path) -> Path:
    """Factory for a pack with multiple agent roles."""
    pack = root / "acme-platform-ops"
    # ... creates sre-platform and mlops-training roles ...
    return pack

# From test_team_mapping.py
def create_team_pack(root: Path) -> Path:
    """Factory for a pack with team definitions."""
    pack = root / "acme-platform-ops"
    # ... creates platform-ops team with two roles ...
    return pack
```

**Location:**
- Fixtures defined in same test file (no conftest.py)
- Factories are test-local helper functions
- Use pytest's built-in `tmp_path` fixture for filesystem

**Pattern:**
```python
def test_example(tmp_path: Path) -> None:
    # Create fixture using factory
    pack_dir = create_docker_cleanup_pack(tmp_path)
    
    # Load and test
    pack = load_pack(pack_dir)
    validate_pack(pack)
    
    # Assert
    assert pack.name == "docker-disk-cleanup"
```

## Coverage

**Requirements:** None enforced (no coverage configuration in `pyproject.toml`)

**View Coverage:**
```bash
# Not configured, but would use:
pytest --cov=aoh --cov-report=html  # With pytest-cov plugin
```

## Test Types

**Unit Tests:**
- Scope: Single functions and small modules
- Approach: Direct function calls with simple inputs
- Examples: `load_role()`, `_as_list()`, `_optional_str()` (though these aren't isolated unit tests, they're tested indirectly)
- Testing validates correct parsing and validation behavior

**Integration Tests:**
- Scope: Multi-module workflows (load → validate → generate/install)
- Approach: Create full pack structure, run CLI or adapter functions
- Examples: `test_init_pack_creates_valid_starter_pack()`, `test_generate_hermes_adapter_materializes_hermes_skills_and_instructions()`
- Tests validate complete workflows end-to-end

**E2E Tests:**
- Framework: Not explicitly used
- Real filesystem pack loading tests exist: `test_core_docker_disk_cleanup_pack_is_valid()`, `test_install_hermes_agent_creates_profile_with_skill_and_launcher()`
- These load actual packs from `collections/` and `examples/` directories, not fixtures

## Common Patterns

**Async Testing:**
Not applicable (no async code in codebase)

**Error Testing:**
Tests verify exception behavior:

```python
# From test_pack_validation.py
def test_validate_pack_rejects_workflow_references_to_missing_artifacts(tmp_path: Path) -> None:
    pack_dir = create_docker_cleanup_pack(tmp_path)
    workflow = pack_dir / "workflows/docker-disk-cleanup.yaml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("docker-readonly", "missing-runtime"),
        encoding="utf-8",
    )
    
    pack = load_pack(pack_dir)
    
    try:
        validate_pack(pack)
    except PackError as exc:
        assert "missing runtime requirement `missing-runtime`" in str(exc)
    else:
        raise AssertionError("validate_pack should reject unresolved workflow references")
```

**Assertion Patterns:**
```python
# Existence checks
assert (pack_dir / "AOH.yaml").exists()

# Collection assertions
assert pack.skills == ["docker-disk-cleanup"]
assert pack.agent_roles == ["ops-triage-lead"]

# String content checks
assert "Docker Disk Cleanup" in skill_file.read_text(encoding="utf-8")
assert "ops-triage-lead" in command_file.read_text(encoding="utf-8")

# Exit code checks
assert exit_code == 0

# Truthiness
assert result.runtime == "hermes"
```

## Test Coverage Overview

**Covered Areas:**
- CLI command routing and option parsing: `test_cli.py`
- Pack discovery and validation: `test_pack_validation.py`
- Agent role loading and filtering: `test_role_mapping.py`
- Team composition and role mapping: `test_team_mapping.py`
- Hermes adapter generation: `test_pack_validation.py`, `test_hermes_agent.py`
- Hermes skill installation: `test_hermes_install.py`
- Real pack loading from collections: `test_core_collection.py`, `test_hermes_agent.py`, `test_hermes_install.py`

**Not Explicitly Tested:**
- `authoring.py` (pack template generation) - covered indirectly via CLI test
- `_write()` file writing utility - covered indirectly via fixture creation
- Error message exact formatting - some error paths tested, others assumed reliable

---

*Testing analysis: 2026-07-14*

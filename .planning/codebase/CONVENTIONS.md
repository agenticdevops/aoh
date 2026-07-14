# Coding Conventions

**Analysis Date:** 2026-07-14

## Naming Patterns

**Files:**
- Python modules use lowercase with hyphens for multi-word names: `pack.py`, `authoring.py`, `hermes.py`
- Test files follow `test_*.py` pattern: `test_cli.py`, `test_pack_validation.py`
- Helper/fixture functions are prefixed with underscore: `_read_yaml()`, `_write()`, `_as_list()`
- Configuration/YAML-based files use UPPERCASE dotted names: `AOH.yaml`, `SKILL.md`, `SOUL.md`

**Functions:**
- Snake_case for all functions: `load_pack()`, `validate_pack()`, `install_hermes_agent()`
- Private functions prefixed with underscore: `_discover_skills()`, `_validate_skill()`, `_optional_str()`
- Verb-first naming for actions: `load_*`, `create_*`, `install_*`, `generate_*`, `validate_*`
- Plural names for discovery/list functions: `_discover_skills()`, `_discover_yaml_names()`

**Variables:**
- Snake_case throughout: `pack_root`, `manifest_path`, `profile_dir`, `selected_skills`
- Type hints used everywhere: `pack: Pack`, `output_dir: Path | str`, `role: AgentRole | None`
- Descriptive names preferred over abbreviations: `manifest` not `mani`, `workflow` not `wf`

**Types:**
- Dataclasses used for domain objects: `Pack`, `AgentRole`, `Team`, `AdapterResult`
- Frozen dataclasses (`@dataclass(frozen=True)`) for immutable value objects
- PascalCase for class names: `Pack`, `AgentRole`, `Team`, `PackError`
- Exception classes inherit from standard exceptions: `PackError(ValueError)`

**Constants:**
- UPPERCASE for module-level constants like `PROJECT_ROOT = Path(__file__).resolve().parents[1]`

## Code Style

**Formatting:**
- No explicit formatter configured; follows implicit PEP 8 style
- 4-space indentation consistently applied
- Line breaks: no strict line length enforcement visible, but generally compact
- Docstrings: triple-quoted strings at module and class level

**Imports:**
- `from __future__ import annotations` at the top of every module (enables PEP 563 deferred annotation evaluation)
- Standard library imports first
- Third-party imports (`yaml`, `json`) after stdlib
- Project imports last (`from aoh.pack import ...`)
- No `import *` usage

**Linting:**
- No `.eslintrc`, `.flake8`, `pylint` config detected
- No explicit formatter config (no `.prettierrc`, `black.toml`, `ruff.toml`)
- Relies on implicit PEP 8 compliance in code review

## Import Organization

**Order:**
1. `from __future__ import` (type hint deferred evaluation)
2. Standard library (`pathlib`, `dataclasses`, `json`, `os`, `sys`, `argparse`, `textwrap`, `shutil`)
3. Third-party (`yaml`)
4. Project imports (`from aoh.pack import ...`, `from aoh.adapters.hermes import ...`)

**Path Aliases:**
- No path aliases configured (`tsconfig` not applicable)
- Absolute imports from `aoh.*` throughout

**Example from `src/aoh/cli.py`:**
```python
from __future__ import annotations

import argparse
from pathlib import Path

from aoh.adapters.hermes import (
    generate_hermes_adapter,
    install_hermes_agent,
    install_hermes_pack,
    install_hermes_team,
)
from aoh.authoring import create_pack
from aoh.pack import PackError, load_pack, validate_pack
```

## Error Handling

**Patterns:**
- Custom exception `PackError(ValueError)` for domain-specific errors in `src/aoh/pack.py`
- Exceptions are raised early with descriptive messages: `raise PackError("AOH.yaml apiVersion must be openagentix.io/v1alpha1")`
- Caught specifically in CLI: `except PackError as exc:` then print and return exit code
- No bare `except:` clauses; always specify exception type
- Error propagation is explicit: caller decides whether to handle or propagate

**Example from `src/aoh/pack.py`:**
```python
class PackError(ValueError):
    """Raised when an AOH pack is invalid."""

# Usage:
if manifest.get("apiVersion") != "openagentix.io/v1alpha1":
    raise PackError("AOH.yaml apiVersion must be openagentix.io/v1alpha1")

# In CLI (src/aoh/cli.py):
except PackError as exc:
    print(f"invalid AOH pack: {exc}")
    return 1
```

## Logging

**Framework:** `print()` for user-facing output; no logging framework (no `logging` module)

**Patterns:**
- Print statements for CLI feedback: `print(f"created AOH pack: {target}")`
- Formatted strings with f-strings: `print(f"valid AOH pack: {pack.name}")`
- Exit codes signal success/failure to shell: `return 0` (success), `return 1` (error), `return 2` (unknown command)
- No debug/info/error logging levels; everything is user-visible output

**Example from `src/aoh/cli.py`:**
```python
print(f"created AOH pack: {target}")
print(f"valid AOH pack: {pack.name}")
print(f"invalid AOH pack: {exc}")
```

## Comments

**When to Comment:**
- Class/module docstrings explain purpose: `"""Raised when an AOH pack is invalid."""`
- Rare inline comments only for non-obvious logic; code is generally self-documenting
- No TODO/FIXME comments found in production code
- Comments explain the "why", not the "what"

**JSDoc/TSDoc:**
- Not applicable (Python, not TypeScript/JavaScript)
- Python uses docstrings instead

**Example from `src/aoh/pack.py`:**
```python
@dataclass(frozen=True)
class Pack:
    """Domain object representing an AOH pack with all discovered artifacts."""
    root: Path
    name: str
    manifest: dict[str, Any]
    # ... (attributes are self-documenting via type hints)
```

## Function Design

**Size:** Prefer small, focused functions. Example functions are 5-50 lines:
- `load_pack()`: 28 lines (main discovery logic)
- `_discover_skills()`: 7 lines (single responsibility)
- `validate_pack()`: 70 lines (complex, but each section is clearly delineated)

**Parameters:**
- Use `*` to force keyword-only arguments for optional parameters: `def install_hermes_pack(..., *, category: str = "aoh", skills: list[str] | None = None)`
- Type hints on all parameters and return types
- Default values for optional parameters
- No positional varargs (`*args`) or keyword varargs (`**kwargs`) used

**Return Values:**
- Single return type per function; no `None | Value` returns unless necessary
- When multiple values needed, return a dataclass: `AdapterResult` in `src/aoh/adapters/hermes.py`
- Early returns for error conditions (not used; exceptions preferred)

**Example from `src/aoh/adapters/hermes.py`:**
```python
def install_hermes_pack(
    pack: Pack,
    skills_dir: Path | str,
    *,
    category: str = "aoh",
    skills: list[str] | None = None,
) -> AdapterResult:
    """Install skills into a Hermes skills directory with optional filtering."""
    target = Path(skills_dir) / category
    generated: list[Path] = []
    selected_skills = skills or pack.skills
    # ... logic ...
    return AdapterResult(runtime="hermes", output_dir=target, generated_files=generated)
```

## Module Design

**Exports:**
- Use `__all__` in main `__init__.py`: `__all__ = ["__version__"]` in `src/aoh/__init__.py`
- No `__all__` in other modules; all public functions are implicitly exported
- Namespace organization: `aoh.pack`, `aoh.cli`, `aoh.adapters.hermes`, `aoh.authoring`

**Barrel Files:**
- `src/aoh/__init__.py` exports only `__version__`, not domain objects
- Domain objects imported directly: `from aoh.pack import Pack, load_pack`
- Adapters imported directly: `from aoh.adapters.hermes import install_hermes_agent`

**Organization:**
- One primary responsibility per module
- `pack.py`: Pack model, loading, validation
- `cli.py`: Argument parsing and command routing
- `adapters/hermes.py`: Hermes-specific code generation and installation
- `authoring.py`: Pack template generation

---

*Convention analysis: 2026-07-14*

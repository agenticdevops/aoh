# Technology Stack

**Analysis Date:** 2026-07-14

## Languages

**Primary:**
- Python 3.11+ - Core language for all implementation and CLI tools

## Runtime

**Environment:**
- Python 3.11 or higher (specified in `pyproject.toml`)

**Package Manager:**
- uv (fast Python package installer)
- Lockfile: `uv.lock` (present, tracked in version control)

## Frameworks

**Core:**
- None (standard library based)

**CLI:**
- `argparse` (Python standard library) - Command-line argument parsing in `src/aoh/cli.py`

**Data/Config:**
- `PyYAML` 6.0+ - YAML parsing and serialization for pack manifests and pack definitions

**Testing:**
- `pytest` 8.0+ - Test runner and framework

## Key Dependencies

**Critical:**
- `PyYAML` 6.0.3 - Parses AOH.yaml manifests, skill frontmatter, workflow definitions, and role/team specifications. Essential for pack validation and loading (`src/aoh/pack.py`)

**Development:**
- `pytest` 9.1.1 - Test execution framework
- `colorama` 0.4.6 - Terminal color support (transitive via pytest)
- `pluggy` 1.6.0 - Plugin system for pytest (transitive)
- `pygments` 2.20.0 - Syntax highlighting (transitive via pytest)
- `packaging` 26.2 - Version handling (transitive)

## Configuration

**Environment:**
- No environment variables are required for basic operation
- No `.env` files detected (not used)

**Build:**
- `pyproject.toml` at project root defines project metadata, dependencies, and build configuration
- Uses `setuptools` as build backend (specified in `[build-system]`)
- Package discovery configured in `[tool.setuptools.packages.find]` with `where = ["src"]`

**CLI Entry Point:**
- `aoh` console script defined in `pyproject.toml` pointing to `aoh.cli:main`

## Platform Requirements

**Development:**
- Python 3.11+ with uv package manager
- Unix-like shell (bash/zsh) for running tests and CLI
- Text editor for modifying pack YAML/markdown files

**Production:**
- Python 3.11+
- No external services required
- File system access for reading/writing pack definitions and generated outputs

## Project Structure

**Source Code:**
- `src/aoh/` - Main package containing core logic
  - `cli.py` - Command-line interface and subcommand routing
  - `pack.py` - Pack loading, validation, and data models
  - `authoring.py` - Pack creation utilities
  - `adapters/hermes.py` - Hermes runtime adapter

**Tests:**
- `tests/` - Test suite using pytest

**Documentation:**
- `README.md` - Project overview and usage guide
- `docs/` - Additional documentation (if present)

**Examples:**
- `examples/acme-platform-ops/` - Example pack with team/role structure
- `collections/core/docker-disk-cleanup/` - Core collection example

---

*Stack analysis: 2026-07-14*

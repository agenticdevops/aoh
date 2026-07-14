# Codebase Structure

**Analysis Date:** 2026-07-14

## Directory Layout

```
aoh/
├── .planning/                      # GSD planning and analysis docs
│   └── codebase/
├── collections/                    # Git-backed packs (shared capabilities)
│   └── core/
│       └── docker-disk-cleanup/    # Core vertical slice example
├── examples/                        # Full example packs
│   └── acme-platform-ops/          # Multi-role team example
├── src/aoh/                        # Python source code
│   ├── __init__.py
│   ├── authoring.py                # Pack creation (init-pack command)
│   ├── cli.py                      # Main command-line interface
│   ├── pack.py                     # Pack loading, validation, models
│   └── adapters/
│       ├── __init__.py
│       └── hermes.py               # Hermes runtime adapter
├── tests/                          # Test suite
│   ├── test_cli.py
│   ├── test_core_collection.py
│   ├── test_hermes_agent.py
│   ├── test_hermes_install.py
│   ├── test_pack_validation.py
│   ├── test_role_mapping.py
│   └── test_team_mapping.py
├── docs/                           # Project documentation
│   ├── authoring.md                # Guide for creating packs
│   ├── spec.md                     # AOH spec and concepts
│   ├── hermes-adapter.md           # Hermes adapter details
│   └── plans/                      # Design and implementation docs
├── pyproject.toml                  # Python project configuration
├── README.md                       # Project overview
└── uv.lock                         # Locked dependency versions
```

## Directory Purposes

**`src/aoh/`:**
- Purpose: Core AOH library code
- Contains: Pack loading, validation, CLI, adapters
- Key files: `pack.py` (models), `cli.py` (entry point), `authoring.py` (templates)

**`src/aoh/adapters/`:**
- Purpose: Runtime-specific adapters (Hermes, future: Goose, Codex, OpenCode)
- Contains: Adapter implementations for each runtime
- Key files: `hermes.py` (primary adapter)

**`collections/`:**
- Purpose: Shared, versioned AOH packs checked into version control
- Contains: Ready-to-use capability collections
- Pattern: `collections/{category}/{pack-name}/AOH.yaml` + artifacts
- Key examples: `collections/core/docker-disk-cleanup/`

**`examples/`:**
- Purpose: Full example packs demonstrating concepts
- Contains: Multi-role team examples, realistic scenarios
- Key examples: `examples/acme-platform-ops/` (SRE, DevOps, MLOps roles)

**`tests/`:**
- Purpose: Test suite for all functionality
- Contains: Unit tests for pack validation, adapter generation, CLI commands
- Pattern: `test_*.py` files with pytest conventions

**`docs/`:**
- Purpose: Human-readable documentation
- Contains: Authoring guides, specifications, adapter details, design docs
- Key files: `spec.md` (concepts), `authoring.md` (how to create packs)

## Key File Locations

**Entry Points:**
- `src/aoh/cli.py:main()` - CLI entry point, all command dispatch
- `src/aoh/__init__.py` - Package version metadata

**Configuration:**
- `pyproject.toml` - Python project metadata, dependencies, pytest config
- Pack manifests: `AOH.yaml` (each pack root)

**Core Logic:**
- `src/aoh/pack.py` - Pack loading, validation, models (Pack, AgentRole, Team dataclasses)
- `src/aoh/adapters/hermes.py` - Hermes adapter (profile generation, skill installation)
- `src/aoh/authoring.py` - Pack initialization templates

**Testing:**
- `tests/test_pack_validation.py` - Pack discovery, validation, referential integrity
- `tests/test_hermes_agent.py` - Hermes adapter agent profile generation
- `tests/test_hermes_install.py` - Hermes skill installation
- `tests/test_role_mapping.py` - AgentRole loading and spec validation
- `tests/test_team_mapping.py` - Team loading and spec validation
- `tests/test_core_collection.py` - Core collection pack validation
- `tests/test_cli.py` - CLI command interface

## Naming Conventions

**Files:**
- Python source: snake_case.py (e.g., `pack.py`, `hermes.py`)
- Packs: kebab-case-with-hyphens as directories (e.g., `docker-disk-cleanup`, `acme-platform-ops`)
- Pack manifests: `AOH.yaml` (always)
- Skills: `SKILL.md` (always, with YAML frontmatter)
- Workflows: kebab-case.yaml (e.g., `platform-sre-triage.yaml`)
- Agent roles: kebab-case.yaml (e.g., `sre-platform.yaml`)
- Teams: kebab-case.yaml (e.g., `platform-ops.yaml`)
- Models: kebab-case.yaml (e.g., `worker-codex.yaml`)
- Runtime requirements: kebab-case.yaml (e.g., `shell-readonly.yaml`)
- Evals: kebab-case.yaml (e.g., `docker-disk-cleanup-basic.yaml`)

**Directories:**
- Pack collections: `collections/{category}/{pack-name}/`
- Examples: `examples/{project-name}/`
- Skills: `skills/{skill-name}/`
- Workflows: `workflows/`
- Agents: `agents/`
- Models: `models/`
- Runtime requirements: `runtime-requirements/`
- Evals: `evals/`
- Teams: `teams/`

## Where to Add New Code

**New Feature (CLI Command):**
- Implementation: Add subcommand handler to `src/aoh/cli.py:main()` (parse args, dispatch)
- Handler implementation: Add function to `src/aoh/adapters/` or create new module
- Tests: Add test_*.py in `tests/` directory with fixtures reusing pack creation patterns

**New Adapter (e.g., Goose):**
- Implementation: Create `src/aoh/adapters/goose.py` following Hermes adapter pattern
- Entry point: Add CLI commands in `src/aoh/cli.py` (e.g., `install-goose-team`, `adapt-goose`)
- Tests: Create `tests/test_goose_*.py` files mirroring hermes test patterns

**New Pack (Collection):**
- Location: `collections/{category}/{pack-name}/`
- Structure: Create directory with AOH.yaml + subdirectories for artifacts
- Use authoring: Run `uv run aoh init-pack {name} --output collections/local/{name}` to bootstrap
- Validation: Run `uv run aoh validate collections/{category}/{pack-name}`

**New Pack (Example):**
- Location: `examples/{org}-{project}/`
- Structure: Same as collection packs
- Purpose: Demonstrate multi-role, multi-skill setup
- Validation: Run `uv run aoh validate examples/{org}-{project}`

**Utilities/Helpers:**
- If pack-agnostic: Add to `src/aoh/pack.py` helper section (e.g., _discover_skills, _validate_skill)
- If adapter-specific: Add to appropriate adapter module (e.g., `src/aoh/adapters/hermes.py`)
- If CLI-specific: Keep in `src/aoh/cli.py`

## Special Directories

**`.planning/codebase/`:**
- Purpose: GSD codebase analysis documents (ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md)
- Generated: Yes (by GSD orchestrator)
- Committed: No (git-ignored for now, may be committed later)

**`docs/plans/`:**
- Purpose: Design and implementation planning documents
- Generated: Yes (manually or by GSD planning tools)
- Committed: Yes (part of project record)

**`.pytest_cache/`, `__pycache__/`:**
- Purpose: Build artifacts from pytest and Python bytecode
- Generated: Yes (during test runs)
- Committed: No (git-ignored)

**`.venv/`, `venv/`:**
- Purpose: Python virtual environment
- Generated: Yes (by `uv venv`)
- Committed: No (git-ignored)

## Pack Structure Template

All packs (collections and examples) follow this structure:

```
{pack-root}/
├── AOH.yaml                        # Pack manifest (metadata, apiVersion, kind)
├── agents/                         # AgentRole definitions
│   ├── {role1}.yaml
│   ├── {role2}.yaml
│   └── ...
├── teams/                          # Team definitions (optional)
│   ├── {team1}.yaml
│   └── ...
├── skills/                         # Reusable capabilities
│   ├── {skill1}/
│   │   ├── SKILL.md               # Skill definition with YAML frontmatter
│   │   └── [scripts/]             # Optional shell scripts
│   ├── {skill2}/
│   └── ...
├── workflows/                      # Executable workflows
│   ├── {workflow1}.yaml
│   ├── {workflow2}.yaml
│   └── ...
├── models/                         # ModelProfile definitions
│   ├── {model1}.yaml
│   └── ...
├── runtime-requirements/           # RuntimeRequirement definitions
│   ├── {requirement1}.yaml
│   └── ...
└── evals/                          # Eval definitions
    ├── {eval1}.yaml
    └── ...
```

## API Boundaries

**Pack Model → Adapter:**
- Input: Pack dataclass with root, name, manifest, lists of artifacts
- Contract: Adapter receives validated pack; may call load_role/load_team for detailed specs
- Output: AdapterResult with runtime, output_dir, generated_files list

**CLI → Pack Module:**
- Input: Path arguments, command flags
- Contract: load_pack() returns Pack or raises PackError; validate_pack() raises or returns None
- Output: Printed messages, exit codes

**CLI → Adapter:**
- Input: Pack, output directories, configuration (provider, model, cwd, etc.)
- Contract: Adapter functions return AdapterResult; may raise PackError
- Output: Files written to filesystem, result object with file list

---

*Structure analysis: 2026-07-14*

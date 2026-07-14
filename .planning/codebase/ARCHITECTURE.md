# Architecture

**Analysis Date:** 2026-07-14

## Pattern Overview

**Overall:** AOH (Agentic Ops Harness) is a **declarative config compiler pattern** that transforms portable YAML-based organizational and capability definitions into runtime-specific agent profiles and skill installations.

**Key Characteristics:**
- Single source of truth: YAML-based pack definitions (AOH.yaml files)
- Engine-neutral design: Adapters compile packs into runtime-specific formats (Hermes first)
- Hierarchical organizational model: Org/Project → Team → Role → Skills/Workflows
- Declarative validation: All artifact references resolved before runtime compilation
- Skills as first-class citizens: Reusable, composable operational capabilities with YAML frontmatter

## Layers

**Pack Definition Layer:**
- Purpose: Define the portable organizational and capability structure
- Location: Pack root directories (e.g., `collections/`, `examples/`)
- Contains: AOH.yaml manifest, skills/, agents/, workflows/, models/, runtime-requirements/, evals/, teams/
- Depends on: YAML syntax, file system conventions
- Used by: Adapter layer, validation engine

**Validation Layer:**
- Purpose: Enforce referential integrity and required artifacts
- Location: `src/aoh/pack.py` (load_pack, validate_pack functions)
- Contains: Pack discovery, artifact loading, cross-reference verification
- Depends on: Pack definition layer
- Used by: CLI, adapter layer

**Adapter Layer:**
- Purpose: Compile portable pack definitions into runtime-specific formats
- Location: `src/aoh/adapters/hermes.py`
- Contains: generate_hermes_adapter, install_hermes_pack, install_hermes_agent, install_hermes_team
- Depends on: Validation layer, Pack model
- Used by: CLI commands

**CLI Layer:**
- Purpose: User-facing command interface for pack operations
- Location: `src/aoh/cli.py`
- Contains: Argument parsing, command dispatch, error reporting
- Depends on: Pack module, authoring module, adapter layer
- Used by: End users, automation scripts

**Authoring Support Layer:**
- Purpose: Bootstrap new packs with starter templates
- Location: `src/aoh/authoring.py`
- Contains: create_pack function
- Depends on: File system operations
- Used by: CLI init-pack command

## Data Flow

**Pack Validation Flow:**

1. CLI receives `validate` command with pack path
2. CLI calls `load_pack(path)` → discovers all artifacts via file system glob patterns
3. Pack model populated with lists of: skills, workflows, agent_roles, teams, models, runtime_requirements, evals
4. CLI calls `validate_pack(pack)` → verifies:
   - At least one skill and one workflow exists
   - All skills have valid SKILL.md with YAML frontmatter
   - All workflow specs reference existing skills, agent_roles, model_profiles, runtime_requirements, evals
   - All agent role specs reference existing skills, workflows, runtime_requirements, model_profiles
   - All team specs reference existing agent_roles, model_profiles
5. Returns on success; raises PackError on any broken reference

**Hermes Adapter Installation Flow:**

1. CLI receives `install-hermes-team` with pack path, team name, profile prefix
2. CLI loads and validates pack
3. For each role in the team:
   - Load role spec from `agents/{role-name}.yaml`
   - Install skills directory: `install_hermes_pack(pack, skills_dir, selected_skills=role.skills)`
   - Create profile directory: `{profiles_dir}/{profile_prefix}-{role_name}`
   - Generate config.yaml (Hermes runtime config)
   - Generate SOUL.md (role instructions from role spec)
   - Generate launch.sh (executable entry point)
   - Generate aoh-agent.json (metadata manifest)
4. Result: Role-specific Hermes profiles ready for launch

**Skills Installation Subflow:**

1. For each selected skill:
   - Copy skill directory from `pack.root/skills/{skill}` to `skills_dir/{skill}`
   - Create reference file: `{skill}/references/aoh-workflow.md` (links back to workflow definitions)
2. Generate skill category manifest: `{pack_name}.aoh-hermes.json` (metadata for Hermes skill discovery)

## Key Abstractions

**Pack:**
- Purpose: Root container for all AOH definitions
- Examples: `collections/core/docker-disk-cleanup`, `examples/acme-platform-ops`
- Pattern: Directory with AOH.yaml manifest and artifact subdirectories

**AgentRole:**
- Purpose: A real-world operational role (SRE, DevOps, MLOps engineer)
- Examples: `sre-platform`, `devops-automation`, `mlops-training`
- Pattern: YAML file in `agents/{name}.yaml` with spec containing skills, workflows, runtime_requirements, model_profile, responsibilities

**Team:**
- Purpose: Group of related agent roles (e.g., platform-ops team)
- Examples: `platform-ops` containing sre-platform + devops-automation + mlops-training
- Pattern: YAML file in `teams/{name}.yaml` with spec containing roles list, org, businessUnit, project metadata

**Skill:**
- Purpose: Reusable agent-usable operational capability
- Examples: `docker-disk-cleanup`, `service-health-report`, `terraform-plan-review`
- Pattern: Directory `skills/{name}/` with SKILL.md (YAML frontmatter + markdown content)
- Frontmatter requires: name, description
- Content: Workflow steps, context, and guidance

**Workflow:**
- Purpose: Executable operational flow combining skills, role context, model requirements, and evals
- Examples: `platform-sre-triage`, `devops-release-automation`
- Pattern: YAML file in `workflows/{name}.yaml` with spec containing skills list, agentRole, modelProfile, runtimeRequirements, evals
- Connects skills to roles: bridges declarative skills with role execution context

**ModelProfile:**
- Purpose: Declares model intent and characteristics for an execution context
- Examples: `local-worker` (low-cost inference), `worker-codex` (GPT-5.4 codex)
- Pattern: YAML file in `models/{name}.yaml` with spec containing intent field

**RuntimeRequirement:**
- Purpose: Declares tool/capability needs for safe execution
- Examples: `shell-readonly` (shell.read capability), `docker-readonly` (docker.read)
- Pattern: YAML file in `runtime-requirements/{name}.yaml` with spec containing capabilities list

**Eval:**
- Purpose: Quality/validation criteria for a workflow execution
- Examples: `docker-disk-cleanup-basic`, `platform-sre-basic`
- Pattern: YAML file in `evals/{name}.yaml` with spec containing prompt field

## Entry Points

**CLI Main Entry:**
- Location: `src/aoh/cli.py:main(argv)`
- Triggers: Direct invocation `aoh` command or `uv run aoh`
- Responsibilities: Parse arguments, dispatch to handlers, format output, manage exit codes

**Pack Loading Entry:**
- Location: `src/aoh/pack.py:load_pack(root)`
- Triggers: Any command that needs pack metadata
- Responsibilities: Discover all artifacts via glob patterns, populate Pack dataclass, raise PackError if pack root structure invalid

**Validation Entry:**
- Location: `src/aoh/pack.py:validate_pack(pack)`
- Triggers: Before any adapter/installation operation
- Responsibilities: Verify referential integrity across all artifacts

**Adapter Entry:**
- Location: `src/aoh/adapters/hermes.py:install_hermes_team(pack, profiles_dir, team_name, ...)`
- Triggers: `install-hermes-team` CLI command
- Responsibilities: Iterate teams and roles, install role-specific profiles with skills and instructions

## Error Handling

**Strategy:** Fail-fast validation with descriptive error messages. PackError raised for all integrity violations.

**Patterns:**
- Invalid YAML syntax → yaml.safe_load raises, wrapped in PackError
- Missing required files → check path.exists(), raise PackError with file path
- Missing metadata fields → check dict.get(), raise PackError with field name and requirement
- Broken references → load_pack populates lists, validate_pack checks against lists, raises PackError with reference path
- Invalid skill frontmatter → parse YAML frontmatter, validate required fields (name, description), raise PackError with field name

## Cross-Cutting Concerns

**Logging:** No logging framework; errors reported via print() to stdout and sys.exit codes. Tests verify output strings.

**Validation:** Centralized in `validate_pack()` function; runs before adapter operations to prevent partial installations.

**Authentication:** None; adapters assume runtime (Hermes, Goose, etc.) handles authentication. AOH only provides declarative shape.

**Configuration:** Adapter config generated from pack + CLI args (provider, model, cwd) → written to Hermes config.yaml with runtime-native format.

---

*Architecture analysis: 2026-07-14*

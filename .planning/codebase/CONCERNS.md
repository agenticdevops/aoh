# Codebase Concerns

**Analysis Date:** 2026-07-14

## Tech Debt

**Path handling and tilde expansion inconsistency:**
- Issue: CLI arguments accept `Path` objects but some default values (e.g., `~/.hermes/profiles`) are not consistently expanded. `argparse` converts to `Path` without expanding `~` until explicitly called with `.expanduser()`.
- Files: `src/aoh/cli.py` (lines 43, 55), `src/aoh/adapters/hermes.py` (line 117)
- Impact: Commands with default profile paths containing `~` will fail unless users expand the path manually. Only `install_hermes_agent` explicitly calls `.expanduser()` on line 117, leaving other functions vulnerable.
- Fix approach: Apply `.expanduser()` consistently to all user-provided `Path` arguments in the argparse handler, or document that tilde expansion requires manual expansion. Alternatively, post-process all `Path` arguments from argparse in the `main()` function before passing to adapter functions.

**Missing error context in YAML parsing:**
- Issue: `_read_yaml()` raises generic `PackError` without showing actual YAML parsing errors. When a YAML file is malformed, the error message doesn't indicate the parsing failure or the line number.
- Files: `src/aoh/pack.py` (lines 246-255)
- Impact: Users debugging broken packs get unhelpful error messages when YAML is invalid. The underlying `yaml.safe_load()` exception is silently swallowed.
- Fix approach: Catch `yaml.YAMLError` explicitly and re-raise as `PackError` with the original error message included. Example: `except yaml.YAMLError as e: raise PackError(f"YAML syntax error in {path}: {e}")`.

**Weak validation of skill file structure:**
- Issue: `_validate_skill()` only checks that SKILL.md has YAML frontmatter and that the frontmatter `name` field matches the directory name. It doesn't validate that the skill's content (the Markdown portion after frontmatter) is well-formed or contains required sections.
- Files: `src/aoh/pack.py` (lines 214-227)
- Impact: Packs can pass validation with incomplete or empty skill documentation. Skills with missing "Workflow", "Overview", or other expected sections are not caught until runtime.
- Fix approach: Extend `_validate_skill()` to check for presence of common Markdown headers (e.g., "## Overview", "## Workflow") or at least ensure the content is not empty. Add a parameter to `validate_pack()` for strict vs. permissive validation if breaking change is unacceptable.

**No cross-pack reference validation:**
- Issue: AOH supports Git-backed packs and teams, but there's no mechanism to validate references to packs from other repositories or to detect breaking changes when a pack is updated.
- Files: `src/aoh/pack.py` (entire module), `src/aoh/authoring.py`
- Impact: Teams using multiple packs cannot ensure that workflows, skills, or roles haven't been renamed or removed in upstream packs.
- Fix approach: Add a `PackRegistry` class that can load and validate multiple pack roots, and a `--registry-paths` flag to CLI commands to enable cross-pack validation.

**No dependency locking for generated artifacts:**
- Issue: When `install_hermes_team()` or `install_hermes_agent()` generates profiles, there's no way to record which version of which pack was used. If a pack is later updated or deleted, installed profiles become orphaned.
- Files: `src/aoh/adapters/hermes.py` (lines 169-218, 106-166)
- Impact: Long-running profiles may reference skills that have been removed or changed in the source pack. Debugging becomes difficult because the generated artifacts don't track their source version.
- Fix approach: Add a `pack_version` or `pack_git_sha` field to `AdapterResult` and include it in all generated `*.json` manifests. Consider adding a `pack.lock` file that records pack state at generation time.

## Known Bugs

**Incorrect handling of paths with spaces in launch.sh:**
- Symptoms: Launch script generated for profiles fails if profile name or cwd contains spaces
- Files: `src/aoh/adapters/hermes.py` (line 328)
- Trigger: Create a profile with a name like "acme platform sre" or use `--cwd "/path with spaces"`
- Workaround: Avoid spaces in profile names and paths. Quote manually in shell if needed.
- Details: Line 328 renders `exec hermes --profile {profile_name}` without quoting. If `profile_name` is "acme-platform sre" (with space), the shell will split it.
- Fix: Use `shlex.quote()` to escape profile names and skill arguments: `shlex.quote(profile_name)` and `",".join(shlex.quote(s) for s in skills)`.

**Skill discovery fails silently if skills/ directory missing:**
- Symptoms: Packs with no `skills/` directory are accepted as valid despite failing validation requirement that "Pack must define at least one skill"
- Files: `src/aoh/pack.py` (lines 204-211, 132-134)
- Trigger: `create_pack()` creates a pack, then manually delete the `skills/` directory, then run `validate_pack()`
- Workaround: Ensure `skills/` directory exists and contains at least one SKILL.md
- Details: `_discover_skills()` returns an empty list if the directory doesn't exist (line 205-206). The validation check on line 133 then fails with a generic message rather than pointing to the missing directory.
- Fix: Explicitly check that the `skills/` directory exists in `load_pack()` or provide a more helpful error message in `validate_pack()`.

**No graceful handling of circular references in workflows:**
- Symptoms: If a workflow references itself or creates a circular dependency through agent roles, validation completes without error
- Files: `src/aoh/pack.py` (lines 132-201)
- Trigger: Create a workflow that references an agent role, then have that role reference a workflow that references the original workflow
- Impact: Generated Hermes profiles may contain confusing or infinite references
- Fix approach: Add cycle detection in `validate_pack()` using a visited set or topological sort.

## Security Considerations

**Arbitrary shell command injection in generated launch.sh:**
- Risk: The launch script template hardcodes `exec hermes ...` without validating provider or model names. If an attacker controls the provider or model arguments to `install_hermes_agent()`, they can inject shell commands.
- Files: `src/aoh/adapters/hermes.py` (lines 258-276, 323-329)
- Current mitigation: None. The function accepts provider and model as strings and writes them directly to config.yaml and launch.sh.
- Impact: Medium - requires attacker to control CLI arguments, which is typically admin-only, but if AOH is wrapped in a service or API, this becomes high-risk.
- Recommendations: 
  - Validate provider and model against a whitelist of known providers (e.g., "openai-codex", "anthropic", etc.)
  - Use `shlex.quote()` for all shell-interpolated values in generated scripts
  - Consider generating Python scripts instead of shell scripts for better control over escaping

**YAML frontmatter parsing accepts arbitrary YAML objects:**
- Risk: `_validate_skill()` uses `yaml.safe_load()` which is safe from arbitrary code execution, but the skill frontmatter could be extended to include fields that are later unsafely processed.
- Files: `src/aoh/pack.py` (line 221)
- Current mitigation: `yaml.safe_load()` is used (not `yaml.load()`)
- Impact: Low for current implementation, but future extensions could be vulnerable. For example, if frontmatter is later used to generate code or run scripts, malicious YAML could be injected.
- Recommendations: 
  - Define a strict schema for skill frontmatter (name, description, author, version)
  - Use a YAML schema validator (e.g., `cerberus` or `pydantic`) to enforce allowed fields
  - Document that only certain fields are supported

**Insufficient validation of user-provided paths:**
- Risk: CLI accepts arbitrary `Path` arguments without checking for traversal attacks (e.g., `--output ../../sensitive`)
- Files: `src/aoh/cli.py` (lines 21, 25, 30, 35-36, 43, 55)
- Current mitigation: None
- Impact: Low - the project appears to be for internal use, but if exposed as a service, an attacker could write files outside intended directories
- Recommendations: 
  - Resolve paths to absolute paths and ensure they fall within a safe parent directory
  - Add an optional `--unsafe-paths` flag if path restriction is too strict for some use cases

## Performance Bottlenecks

**copytree in adapter functions causes unnecessary I/O:**
- Problem: `generate_hermes_adapter()` and `install_hermes_pack()` use `copytree()` to duplicate entire skill directories. For large packs or many skills, this can be slow and consume disk space.
- Files: `src/aoh/adapters/hermes.py` (lines 25, 73)
- Cause: Symlinks or hard links are not used, and there's no option to generate references instead of copies.
- Improvement path: 
  - Add an optional `--link` or `--symlink` flag to avoid copying large files
  - Consider generating manifest files that point to the source pack instead of copying for read-only use cases
  - Benchmark with packs >100MB to identify if this is a real issue

**Manifest JSON files are regenerated on every adapter call:**
- Problem: `install_hermes_pack()` and `install_hermes_team()` regenerate manifests even if the source pack hasn't changed
- Files: `src/aoh/adapters/hermes.py` (lines 82-101, 199-216)
- Cause: No caching or incremental update logic
- Improvement path: Add a `--force` flag and check modification times on the source pack to avoid regeneration. For teams, only regenerate manifests for roles that have changed.

## Fragile Areas

**AgentRole and Team dataclasses have insufficient validation:**
- Files: `src/aoh/pack.py` (lines 28-51)
- Why fragile: The `AgentRole` and `Team` dataclasses are frozen but have no constraints on their fields (e.g., `name` could be empty, `skills` could contain duplicates). Validation happens after instantiation in `validate_pack()`, not at construction time.
- Safe modification: Always call `validate_pack()` immediately after loading a pack. Don't use `AgentRole` or `Team` instances without validation in production code.
- Test coverage: Tests verify that validation catches missing references (e.g., invalid skill names), but don't test that empty or malformed names are caught. Missing tests for:
  - Empty `name` fields
  - Duplicate entries in `skills`, `workflows`, `runtime_requirements` lists
  - Invalid characters in identifiers

**SKILL.md frontmatter parsing is brittle:**
- Files: `src/aoh/pack.py` (lines 214-227)
- Why fragile: The parser splits on `---` delimiters using a simple string split. If a skill's Markdown content contains `---` (common in code blocks showing YAML), the parser will fail.
- Safe modification: Document that `---` is reserved and cannot appear in skill Markdown. Consider using a different delimiter or a YAML parser that handles this natively.
- Test coverage: Tests only cover the happy path. Missing tests for:
  - Markdown content with YAML code blocks containing `---`
  - Malformed frontmatter (e.g., missing closing `---`)
  - Non-UTF-8 encoded files

**File discovery assumes stable directory structure:**
- Files: `src/aoh/pack.py` (lines 204-243)
- Why fragile: Discovery functions (`_discover_skills()`, `_discover_yaml_names()`) assume directories exist and files follow exact naming conventions. A missing directory doesn't fail early, but validation happens later.
- Safe modification: Ensure all expected directories are present before discovery. Add explicit checks in `load_pack()` to fail early if required directories (skills, agents, workflows) are missing.
- Test coverage: Tests don't cover edge cases like:
  - Empty directories
  - Non-YAML files in yaml directories
  - YAML files without the required `kind` or `metadata.name` fields

## Scaling Limits

**Current pack size is micro-scale:**
- Current capacity: Test packs have 3-5 skills, 2-3 workflows, 2-3 roles, 1-2 teams
- Limit: Unknown. The code iterates linearly over all skills, workflows, roles, and teams. With 100+ skills or 50+ roles, validation could become slow. Hermes profile generation would create hundreds of directories.
- Scaling path: 
  - For packs: Break into smaller packs and add registry/dependency management
  - For validation: Add parallel validation using `concurrent.futures`
  - For profile generation: Add batch operations and progress reporting

**No support for pack inheritance or composition:**
- Current capacity: Each pack is isolated. Duplicate skills across packs leads to code duplication.
- Limit: Teams across multiple projects need to share common skills (e.g., "service-health-report" used by both platform and backend teams). Currently requires duplicating skill definitions.
- Scaling path: Add support for pack dependencies or skill inheritance. Example: `skills/inherit-from: common-ops-pack:service-health-report`.

## Dependencies at Risk

**Only PyYAML is required; no version constraints:**
- Risk: `PyYAML>=6.0` is very permissive. Future major versions (e.g., 7.0) could introduce breaking changes (e.g., changing the behavior of `safe_load()` or removing some APIs).
- Current: No pinned versions in `pyproject.toml`, only `>=6.0`
- Impact: Future updates could silently break AOH pack validation
- Migration plan: Pin to a specific minor version (e.g., `PyYAML==6.0.1`) or add CI tests for multiple PyYAML versions. Consider using `ruamel.yaml` if more control is needed.

**pytest as dev-only dependency has no version constraint:**
- Risk: Tests may rely on deprecated pytest APIs. Future versions (e.g., pytest 10.0) might drop compatibility.
- Current: `pytest>=8.0` in dev dependencies
- Impact: CI tests could start failing unexpectedly
- Migration plan: Pin to `pytest==8.1.3` or similar after verifying compatibility

## Missing Critical Features

**No support for pack versioning or releases:**
- Problem: Packs are Git-backed but there's no support for tagging versions, creating releases, or managing breaking changes.
- Blocks: Teams cannot safely upgrade to new pack versions. Distribution of packs to external teams or registries is not possible.
- Approach: Add version field to `AOH.yaml` and changelog validation (similar to semantic versioning best practices). Add a `release` command to CLI.

**No support for pack preview or dry-run:**
- Problem: `install_hermes-*` commands directly generate files with no preview or dry-run mode.
- Blocks: Users cannot see what will be generated before committing changes to disk.
- Approach: Add `--dry-run` flag that prints what would be generated without writing files. Add `--diff` to compare against existing installations.

**No support for skill templates or parameterization:**
- Problem: Skills are static Markdown files. Teams cannot parameterize skills for different environments (e.g., dev vs. prod cluster names).
- Blocks: Skill reuse across teams with different infrastructure is limited.
- Approach: Add Jinja2 templating support to skill Markdown and workflow YAML. Add a `params` field to agent roles and workflows.

**No runtime execution or validation:**
- Problem: AOH validates pack structure but doesn't validate that generated profiles actually work with the target runtime.
- Blocks: Invalid Hermes profiles are only discovered at runtime when hermes fails to load them.
- Approach: Add an `--validate-runtime` flag that attempts to load the generated profile and validate skills are executable.

## Test Coverage Gaps

**No tests for malformed YAML:**
- What's not tested: How the code handles YAML files with syntax errors (unclosed quotes, invalid indentation, circular references)
- Files: `src/aoh/pack.py` (lines 246-255), `src/aoh/authoring.py` (lines 10-104)
- Risk: `yaml.safe_load()` exceptions are not caught and will cause the entire CLI to crash with a traceback instead of a helpful error message
- Priority: High

**No tests for path edge cases:**
- What's not tested: Paths with spaces, unicode characters, symlinks, or very long paths
- Files: `src/aoh/cli.py` (all path arguments), `src/aoh/adapters/hermes.py` (lines 19-56, 59-103, 106-166, 169-218)
- Risk: Generated profiles may fail on systems with unusual directory structures
- Priority: Medium

**No tests for concurrent or parallel operations:**
- What's not tested: Behavior when multiple `aoh install-hermes-*` commands run simultaneously against the same profiles directory
- Files: `src/aoh/adapters/hermes.py` (all functions that write to disk)
- Risk: File contention could cause corrupted or missing generated files
- Priority: Medium

**No tests for large packs:**
- What's not tested: Performance and correctness with packs containing 100+ skills, 50+ roles, or large skill Markdown files
- Files: `src/aoh/pack.py` (validation loop, lines 132-201)
- Risk: Slow validation or memory exhaustion with large packs
- Priority: Low

**No tests for skill Markdown with special content:**
- What's not tested: Skill files with `---` in code blocks, non-UTF-8 encoding, very long files, or missing closing frontmatter delimiter
- Files: `src/aoh/pack.py` (lines 214-227)
- Risk: Silent parsing failures or truncated skill content
- Priority: Medium

**No error case coverage for adapter functions:**
- What's not tested: What happens when `install_hermes_agent()` or `install_hermes_team()` fail partway through (e.g., disk full, permission denied, YAML write error)
- Files: `src/aoh/adapters/hermes.py` (all functions)
- Risk: Partially written profile directories left on disk in broken state
- Priority: Medium

---

*Concerns audit: 2026-07-14*

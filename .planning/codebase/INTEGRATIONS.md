# External Integrations

**Analysis Date:** 2026-07-14

## APIs & External Services

**Hermes Agent Runtime:**
- Hermes - Primary agent execution runtime for AOH packs
  - SDK/Client: Generated via `src/aoh/adapters/hermes.py`
  - Integration: AOH generates Hermes-native profiles, skills directories, and launch scripts
  - Configuration: Profile config (model, provider, max_turns, terminal backend) generated at `install_hermes_agent()`
  - Output: YAML config, SOUL.md instructions, JSON metadata, bash launch scripts

**Agent Model Providers:**
- OpenAI Codex (default) - Referenced in Hermes adapter and CLI examples
  - Model parameter: `--provider openai-codex` (CLI default: `gpt-5.4`)
  - Configuration: Specified during profile creation, written to `config.yaml`
  - Not authenticated at AOH level; auth delegated to Hermes runtime

## Data Storage

**Databases:**
- None used

**File Storage:**
- Local filesystem only
- Pack definitions stored as YAML files
- Generated outputs (skills, profiles, manifests) written to local directories
- No cloud storage integration

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- None at AOH layer
- Authentication delegated to agent runtime (Hermes) and model provider
- Runtime profiles include provider/model specification for Hermes to handle authentication

## Monitoring & Observability

**Error Tracking:**
- None

**Logs:**
- No logging framework integrated
- Errors reported as custom `PackError` exceptions in `src/aoh/pack.py`
- CLI prints error messages to stdout/stderr

## CI/CD & Deployment

**Hosting:**
- Not applicable (AOH is a CLI tool)

**CI Pipeline:**
- pytest runs locally via `uv run pytest`
- No external CI/CD system integration detected

## Environment Configuration

**Required env vars:**
- None - AOH operates without environment variables

**Secrets location:**
- Not applicable - AOH does not manage secrets
- Model API credentials managed by agent runtime, not AOH

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None - AOH is a generation and validation tool, not a service that calls external systems

## Pack-to-Runtime Mapping

**Hermes Adapter Output:**
- Generates `config.yaml` with model provider and agent settings
- Generates `SOUL.md` with agent instructions and role context
- Generates `launch.sh` bash script to invoke Hermes with profile and skills
- Creates manifest files (`aoh-hermes.json`, `aoh-agent.json`, `aoh-team.json`) documenting the pack structure

**Team-Level Generation:**
- `install_hermes_team()` creates one Hermes profile per role in a team
- Each profile includes role-specific skills, workflows, and SOUL instructions
- Team manifest links all profiles with role names and organizational metadata

**Skills Integration:**
- AOH skills copied to Hermes skills directory with workflow reference metadata
- Skills invoked by profile launch script with `--skills` parameter

---

*Integration audit: 2026-07-14*

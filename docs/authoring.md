# Authoring AOH Packs

AOH authoring follows the "Superpowers for Ops" mental model.

## Recommended Flow

1. Pick one concrete ops use case.
2. Create a narrow pack with `uv run aoh init-pack`.
3. Write the skill as the reusable operational technique.
4. Define real org/project roles that own capabilities.
5. Associate each role with only the skills it should use.
6. Write process skills as the composition layer for multi-skill flows.
7. Declare model profiles, runtime requirements, and evals.
8. Validate the pack.
9. Generate runtime output for Hermes.
10. Iterate from eval results and real runtime use.

## Agent-Assisted Authoring

Use `authoring-skills/create-aoh-pack/SKILL.md` with Codex, Claude Code, OpenCode, Hermes, or Goose to generate or revise packs.

The authoring agent should produce portable AOH artifacts first, then runtime-specific adapter notes only when needed.

## Fast Start

```bash
uv run aoh init-pack service-health-report \
  --output collections/local/service-health-report \
  --description "Collect read-only service health diagnostics and summarize risk."

uv run aoh validate collections/local/service-health-report
uv run aoh adapt-hermes collections/local/service-health-report --output /tmp/aoh-service-health-hermes
```

## Role-Scoped Example

The `examples/acme-platform-ops` pack models:

- `sre-platform`: service health and Docker/local runtime diagnostics.
- `devops-automation`: deployment automation, Terraform plan review, and health verification.
- `mlops-training`: ML training job triage and service health.

Create the SRE Hermes agent:

```bash
uv run aoh install-hermes-agent examples/acme-platform-ops \
  --profiles-dir ~/.hermes/profiles \
  --profile acme-platform-sre \
  --role sre-platform \
  --provider openai-codex \
  --model gpt-5.4 \
  --cwd "$PWD"
```

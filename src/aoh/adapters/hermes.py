from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from shutil import copytree

from aoh.pack import AgentRole, Pack, load_role, load_team


@dataclass(frozen=True)
class AdapterResult:
    runtime: str
    output_dir: Path
    generated_files: list[Path]


def generate_hermes_adapter(pack: Pack, output_dir: Path | str) -> AdapterResult:
    target = Path(output_dir)
    generated: list[Path] = []

    skills_target = target / "skills"
    if pack.skills:
        copytree(pack.root / "skills", skills_target, dirs_exist_ok=True)
        generated.extend(sorted(skills_target.glob("*/SKILL.md")))

    commands_dir = target / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    for skill in pack.skills:
        command_file = commands_dir / f"ops-{skill}.md"
        command_file.write_text(_render_command(pack, skill), encoding="utf-8")
        generated.append(command_file)

    manifest_file = target / "aoh-hermes.json"
    manifest_file.write_text(
        json.dumps(
            {
                "runtime": "hermes",
                "pack": pack.name,
                "skills": pack.skills,
                "commands": [f"commands/ops-{skill}.md" for skill in pack.skills],
                "agentRoles": pack.agent_roles,
                "modelProfiles": pack.model_profiles,
                "runtimeRequirements": pack.runtime_requirements,
                "evals": pack.evals,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    generated.append(manifest_file)

    return AdapterResult(runtime="hermes", output_dir=target, generated_files=generated)


def install_hermes_pack(
    pack: Pack,
    skills_dir: Path | str,
    *,
    category: str = "aoh",
    skills: list[str] | None = None,
) -> AdapterResult:
    target = Path(skills_dir) / category
    generated: list[Path] = []
    selected_skills = skills or pack.skills

    for skill in selected_skills:
        source = pack.root / "skills" / skill
        destination = target / skill
        copytree(source, destination, dirs_exist_ok=True)

        reference = destination / "references" / "aoh-pack.md"
        reference.parent.mkdir(parents=True, exist_ok=True)
        reference.write_text(_render_pack_reference(pack), encoding="utf-8")

        generated.append(destination / "SKILL.md")
        generated.append(reference)

    manifest_file = target / f"{pack.name}.aoh-hermes.json"
    manifest_file.write_text(
        json.dumps(
            {
                "runtime": "hermes",
                "pack": pack.name,
                "category": category,
                "installedSkills": selected_skills,
                "agentRoles": pack.agent_roles,
                "modelProfiles": pack.model_profiles,
                "runtimeRequirements": pack.runtime_requirements,
                "evals": pack.evals,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    generated.append(manifest_file)

    return AdapterResult(runtime="hermes", output_dir=target, generated_files=generated)


def install_hermes_agent(
    pack: Pack,
    profiles_dir: Path | str,
    *,
    profile_name: str,
    provider: str,
    model: str,
    cwd: str,
    category: str = "aoh",
    role_name: str | None = None,
) -> AdapterResult:
    profile_dir = Path(profiles_dir).expanduser() / profile_name
    skills_dir = profile_dir / "skills"
    profile_dir.mkdir(parents=True, exist_ok=True)
    role = load_role(pack, role_name) if role_name else None
    selected_skills = role.skills if role and role.skills else pack.skills

    skill_result = install_hermes_pack(pack, skills_dir, category=category, skills=selected_skills)
    config_file = profile_dir / "config.yaml"
    soul_file = profile_dir / "SOUL.md"
    manifest_file = profile_dir / "aoh-agent.json"
    launch_file = profile_dir / "launch.sh"

    config_file.write_text(
        _render_profile_config(provider=provider, model=model, cwd=cwd),
        encoding="utf-8",
    )
    soul_file.write_text(_render_agent_soul(pack, role=role), encoding="utf-8")
    manifest_file.write_text(
        json.dumps(
            {
                "runtime": "hermes",
                "profile": profile_name,
                "pack": pack.name,
                "role": role.name if role else None,
                "skills": selected_skills,
                "provider": provider,
                "model": model,
                "cwd": cwd,
                "launch": str(launch_file),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    launch_file.write_text(
        _render_launch_script(profile_name=profile_name, skills=selected_skills),
        encoding="utf-8",
    )
    os.chmod(launch_file, 0o755)

    generated = [
        config_file,
        soul_file,
        manifest_file,
        launch_file,
        *skill_result.generated_files,
    ]
    return AdapterResult(runtime="hermes", output_dir=profile_dir, generated_files=generated)


def install_hermes_team(
    pack: Pack,
    profiles_dir: Path | str,
    *,
    team_name: str,
    profile_prefix: str,
    provider: str,
    model: str,
    cwd: str,
    category: str = "aoh",
) -> AdapterResult:
    team = load_team(pack, team_name)
    generated: list[Path] = []
    output_dir = Path(profiles_dir).expanduser()

    for role_name in team.roles:
        profile_name = f"{profile_prefix}-{role_name}"
        result = install_hermes_agent(
            pack,
            output_dir,
            profile_name=profile_name,
            provider=provider,
            model=model,
            cwd=cwd,
            category=category,
            role_name=role_name,
        )
        generated.extend(result.generated_files)

    team_manifest = output_dir / f"{profile_prefix}-{team.name}.aoh-team.json"
    team_manifest.write_text(
        json.dumps(
            {
                "runtime": "hermes",
                "pack": pack.name,
                "team": team.name,
                "displayName": team.display_name,
                "org": team.org,
                "businessUnit": team.business_unit,
                "project": team.project,
                "profiles": [f"{profile_prefix}-{role}" for role in team.roles],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    generated.append(team_manifest)
    return AdapterResult(runtime="hermes", output_dir=output_dir, generated_files=generated)


def _render_command(pack: Pack, skill: str) -> str:
    agent_roles = ", ".join(pack.agent_roles) or "the default Hermes session"
    models = ", ".join(pack.model_profiles) or "the active Hermes model profile"
    requirements = ", ".join(pack.runtime_requirements) or "the active Hermes tool configuration"

    return (
        f"# ops-{skill}\n\n"
        f"Use the `{skill}` skill for this AOH command.\n\n"
        f"- AOH pack: `{pack.name}`\n"
        f"- Agent role: {agent_roles}\n"
        f"- Model profile: {models}\n"
        f"- Runtime requirements: {requirements}\n\n"
        "Follow the skill instructions, stay focused, and report any runtime "
        "capability that Hermes cannot satisfy directly.\n"
    )


def _render_pack_reference(pack: Pack) -> str:
    agent_roles = ", ".join(pack.agent_roles) or "default Hermes session"
    models = ", ".join(pack.model_profiles) or "active Hermes model"
    requirements = ", ".join(pack.runtime_requirements) or "active Hermes tools"
    evals = ", ".join(pack.evals) or "none"

    return (
        f"# AOH Pack Metadata: {pack.name}\n\n"
        f"- Agent roles: {agent_roles}\n"
        f"- Model profiles: {models}\n"
        f"- Runtime requirements: {requirements}\n"
        f"- Evals: {evals}\n\n"
        "This file was generated by AOH so Hermes can run the installed skill with "
        "the pack's context nearby.\n"
    )


def _render_profile_config(*, provider: str, model: str, cwd: str) -> str:
    return (
        "model:\n"
        f"  default: {model}\n"
        f"  provider: {provider}\n"
        "agent:\n"
        "  max_turns: 40\n"
        "terminal:\n"
        "  backend: local\n"
        f"  cwd: {cwd}\n"
        "  timeout: 300\n"
        "skills:\n"
        "  external_dirs: []\n"
        "platform_toolsets:\n"
        "  cli:\n"
        "    - terminal\n"
        "    - file\n"
        "    - skills\n"
    )


def _render_agent_soul(pack: Pack, *, role: AgentRole | None = None) -> str:
    if role:
        title = role.display_name
        skills = ", ".join(role.skills)
        requirements = ", ".join(role.runtime_requirements)
        responsibilities = "\n".join(f"- {item}" for item in role.responsibilities)
        org_project = " / ".join(part for part in [role.org, role.project] if part)
        scope = f"- Scope: {org_project}\n" if org_project else ""
        return (
            f"# AOH custom Hermes agent: {title}\n\n"
            "You are an Agentic Ops Harness runtime agent. Stay focused on your assigned "
            "organizational role and prefer the associated AOH skills over generic troubleshooting.\n\n"
            f"- Pack: {pack.name}\n"
            f"- Role: {role.name}\n"
            f"{scope}"
            f"- Purpose: {role.purpose}\n"
            f"- Skills: {skills}\n"
            f"- Runtime requirements: {requirements}\n\n"
            "## Responsibilities\n\n"
            f"{responsibilities}\n\n"
            "Start with read-only inspection unless the skill or user explicitly asks for "
            "a write action and the runtime supports approval.\n"
        )

    skills = ", ".join(pack.skills)
    requirements = ", ".join(pack.runtime_requirements)

    return (
        f"# AOH custom Hermes agent: {pack.name}\n\n"
        "You are an Agentic Ops Harness runtime agent. Stay focused on the installed "
        "AOH pack and prefer the associated skill over generic troubleshooting.\n\n"
        f"- Pack: {pack.name}\n"
        f"- Skills: {skills}\n"
        f"- Runtime requirements: {requirements}\n\n"
        "If the user asks for this pack's capability, load and follow the associated "
        "skill instructions. Start with read-only inspection unless the skill or user "
        "explicitly asks for a write action and the runtime supports approval.\n"
    )


def _render_launch_script(*, profile_name: str, skills: list[str]) -> str:
    skill_args = ",".join(skills)
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"exec hermes --profile {profile_name} --skills {skill_args} chat \"$@\"\n"
    )

from __future__ import annotations

import json
import os
from pathlib import Path
from shutil import copytree

from aoh.adapters._k8s import (
    INHERIT_DIAGNOSTIC as _INHERIT_DIAGNOSTIC,
)
from aoh.adapters._k8s import (
    kubeconfig_merge_shell_expr,
    render_overlay_prepare_script,
    render_provision_script,
    validate_binding_fields,
)
from aoh.adapters.base import ADAPTERS, AdapterResult, MaterializeRequest
from aoh.pack import Binding, Pack, PackError, Role, load_role, load_team

# Re-exported for backward compatibility — AdapterResult now lives in base.py.
__all__ = ["AdapterResult", "HermesAdapter", "install_hermes_agent"]


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
                "roles": pack.roles,
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
                "roles": pack.roles,
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
    binding: Binding | None = None,
    site_name: str | None = None,
) -> AdapterResult:
    if binding is not None:
        if binding.role not in pack.roles:
            raise PackError(
                f"Binding `{binding.name}` references missing role `{binding.role}`"
            )
        if role_name is not None and role_name != binding.role:
            raise PackError(
                f"Binding `{binding.name}` role `{binding.role}` conflicts with --role `{role_name}`"
            )
        if not binding.target.get("kubeContext"):
            raise PackError(
                f"Binding `{binding.name}` target.kubeContext is required for kubernetes targets"
            )
        validate_binding_fields(binding)
        role_name = binding.role

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
    soul_file.write_text(_render_agent_soul(pack, role=role, binding=binding), encoding="utf-8")
    manifest_file.write_text(
        json.dumps(
            {
                "runtime": "hermes",
                "profile": profile_name,
                "pack": pack.name,
                "role": role.name if role else None,
                "binding": (
                    {"name": binding.name, "target": binding.target} if binding else None
                ),
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
    inherit = binding is not None and binding.access == "inherit"

    launch_file.write_text(
        _render_launch_script(
            profile_name=profile_name,
            skills=selected_skills,
            with_kubeconfig=binding is not None,
            inherit=inherit,
        ),
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

    diagnostics: list[str] = []

    if binding is not None:
        if inherit:
            overlay_file = profile_dir / "prepare-overlay.sh"
            overlay_file.write_text(render_overlay_prepare_script(binding), encoding="utf-8")
            os.chmod(overlay_file, 0o755)
            generated.append(overlay_file)
            diagnostics.append(_INHERIT_DIAGNOSTIC)
        else:
            provision_file = profile_dir / "provision.sh"
            provision_file.write_text(render_provision_script(binding, site_name=site_name), encoding="utf-8")
            os.chmod(provision_file, 0o755)
            generated.append(provision_file)

    return AdapterResult(
        runtime="hermes",
        output_dir=profile_dir,
        generated_files=generated,
        diagnostics=diagnostics,
    )


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
    roles = ", ".join(pack.roles) or "the default Hermes session"
    models = ", ".join(pack.model_profiles) or "the active Hermes model profile"
    requirements = ", ".join(pack.runtime_requirements) or "the active Hermes tool configuration"

    return (
        f"# ops-{skill}\n\n"
        f"Use the `{skill}` skill for this AOH command.\n\n"
        f"- AOH pack: `{pack.name}`\n"
        f"- Role: {roles}\n"
        f"- Model profile: {models}\n"
        f"- Runtime requirements: {requirements}\n\n"
        "Follow the skill instructions, stay focused, and report any runtime "
        "capability that Hermes cannot satisfy directly.\n"
    )


def _render_pack_reference(pack: Pack) -> str:
    roles = ", ".join(pack.roles) or "default Hermes session"
    models = ", ".join(pack.model_profiles) or "active Hermes model"
    requirements = ", ".join(pack.runtime_requirements) or "active Hermes tools"
    evals = ", ".join(pack.evals) or "none"

    return (
        f"# AOH Pack Metadata: {pack.name}\n\n"
        f"- Roles: {roles}\n"
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


def _render_agent_soul(
    pack: Pack, *, role: Role | None = None, binding: Binding | None = None
) -> str:
    binding_block = ""
    if binding is not None:
        namespace = binding.target.get("namespace", "default")
        if binding.access == "inherit":
            binding_block = (
                "\n## Binding\n\n"
                f"- Bound cluster (kube context): {binding.target.get('kubeContext')}\n"
                f"- Default namespace: {namespace} (you may inspect other namespaces)\n"
                f"- Access mode: {binding.access}\n\n"
                "**access=inherit**: you are acting with YOUR credentials — the "
                "user's own kubeconfig identity, not a scoped ServiceAccount. The "
                "kubeconfig overlay only pins you to this context and namespace; "
                "it grants no new permissions and removes none. There is NO hard "
                "enforcement boundary in this mode — whatever the user's identity "
                "can do, this session can do. Treat every mutating command with "
                "the same caution you would if the user typed it themselves.\n"
            )
        else:
            binding_block = (
                "\n## Binding\n\n"
                f"- Bound cluster (kube context): {binding.target.get('kubeContext')}\n"
                f"- Default namespace: {namespace} (you may inspect other namespaces)\n"
                "- Access: read-only (get/list/watch) enforced by cluster RBAC. Mutation "
                "attempts will be denied by the API server — report denials as the "
                "guardrail working, not as errors to work around.\n"
            )

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
        ) + binding_block

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
    ) + binding_block


def _render_launch_script(
    *,
    profile_name: str,
    skills: list[str],
    with_kubeconfig: bool = False,
    inherit: bool = False,
) -> str:
    skill_args = ",".join(skills)
    if not with_kubeconfig:
        kubeconfig_line = ""
    elif inherit:
        merge_expr = kubeconfig_merge_shell_expr('$(cd "$(dirname "$0")" && pwd)')
        kubeconfig_line = f'export KUBECONFIG="{merge_expr}"\n'
    else:
        kubeconfig_line = (
            'export KUBECONFIG="$(cd "$(dirname "$0")" && pwd)/kubeconfig"\n'
        )
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"{kubeconfig_line}"
        f"exec hermes --profile {profile_name} --skills {skill_args} chat \"$@\"\n"
    )


class HermesAdapter:
    """RuntimeAdapter conformance wrapper around the existing Hermes install path.

    The `RuntimeAdapter` contract (base.py) requires `materialize` to write
    into EXACTLY `request.output_dir` — no extra nesting level. The legacy
    `install_hermes_agent` function nests output under
    `<profiles_dir>/<profile_name>/` and its signature/behavior must stay
    untouched (legacy CLI paths depend on it). This wrapper reconciles the
    two by passing `profiles_dir=request.output_dir.parent` and
    `profile_name=request.output_dir.name`, so the legacy function's nesting
    lands exactly back on `request.output_dir`.
    """

    name = "hermes"

    def materialize(self, request: MaterializeRequest) -> AdapterResult:
        pack = request.pack
        provider = request.options.get("provider", "openai-codex")
        model = request.model_hint or "gpt-5.4"
        cwd = request.workdir or str(Path.cwd())
        site_name = request.options.get("site_name")
        output_dir = Path(request.output_dir)

        result = install_hermes_agent(
            pack,
            output_dir.parent,
            profile_name=output_dir.name,
            provider=provider,
            model=model,
            cwd=cwd,
            role_name=request.role_name,
            binding=request.binding,
            site_name=site_name,
        )

        generated_files = sorted(p for p in output_dir.rglob("*") if p.is_file())
        artifact_map = _hermes_artifact_map(pack, request, output_dir)

        return AdapterResult(
            runtime="hermes",
            output_dir=output_dir,
            generated_files=generated_files,
            diagnostics=result.diagnostics,
            artifact_map=artifact_map,
        )


def _hermes_artifact_map(
    pack: Pack, request: MaterializeRequest, output_dir: Path
) -> dict[str, str]:
    """Map canonical pack-relative skill files -> their materialized path.

    Hermes lays installed skills out at `skills/aoh/<skill>/...` under the
    profile dir (see `install_hermes_pack`). Only files that physically
    originated in the pack's `skills/<skill>/` tree are included — the
    synthetic `references/aoh-pack.md` reference file `install_hermes_pack`
    generates per skill is NOT pack-sourced and is excluded.
    """

    role = load_role(pack, request.role_name) if request.role_name else None
    if role is None and request.binding is not None:
        role = load_role(pack, request.binding.role)
    selected_skills = role.skills if role and role.skills else pack.skills

    artifact_map: dict[str, str] = {}
    for skill in selected_skills:
        source_dir = pack.root / "skills" / skill
        if not source_dir.is_dir():
            continue
        for source_path in sorted(source_dir.rglob("*")):
            if not source_path.is_file():
                continue
            rel = source_path.relative_to(source_dir).as_posix()
            canonical = f"skills/{skill}/{rel}"
            materialized = f"skills/aoh/{skill}/{rel}"
            if (output_dir / materialized).is_file():
                artifact_map[canonical] = materialized

    return artifact_map


ADAPTERS["hermes"] = HermesAdapter()

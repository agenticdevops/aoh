from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class PackError(ValueError):
    """Raised when an AOH pack is invalid."""


@dataclass(frozen=True)
class Pack:
    root: Path
    name: str
    manifest: dict[str, Any]
    skills: list[str]
    roles: list[str]
    teams: list[str]
    model_profiles: list[str]
    runtime_requirements: list[str]
    evals: list[str]


@dataclass(frozen=True)
class Role:
    name: str
    display_name: str
    org: str | None
    project: str | None
    purpose: str
    skills: list[str]
    runtime_requirements: list[str]
    model_profile: str | None
    responsibilities: list[str]


@dataclass(frozen=True)
class Team:
    name: str
    display_name: str
    org: str | None
    business_unit: str | None
    project: str | None
    purpose: str
    roles: list[str]
    default_model_profile: str | None


def load_pack(root: Path | str) -> Pack:
    pack_root = Path(root)
    manifest_path = pack_root / "AOH.yaml"
    manifest = _read_yaml(manifest_path)

    api_version = manifest.get("apiVersion")
    if api_version == "openagentix.io/v1alpha1":
        raise PackError(
            "AOH.yaml apiVersion openagentix.io/v1alpha1 is no longer supported — "
            "see docs/spec.md migration notes"
        )
    if api_version != "openagentix.io/v1alpha2":
        raise PackError("AOH.yaml apiVersion must be openagentix.io/v1alpha2")
    if manifest.get("kind") != "Pack":
        raise PackError("AOH.yaml kind must be Pack")

    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("name"):
        raise PackError("AOH.yaml metadata.name is required")

    if (pack_root / "workflows").exists():
        raise PackError(
            "workflows/ is no longer supported — convert workflows to process skills "
            "(see docs/spec.md migration notes)"
        )

    if (pack_root / "agents").exists():
        raise PackError(
            "agents/ was renamed to roles/ and kind AgentRole to Role "
            "(see docs/spec.md migration notes)"
        )

    return Pack(
        root=pack_root,
        name=str(metadata["name"]),
        manifest=manifest,
        skills=_discover_skills(pack_root / "skills"),
        roles=_discover_yaml_names(pack_root / "roles", "Role"),
        teams=_discover_yaml_names(pack_root / "teams", "Team"),
        model_profiles=_discover_yaml_names(pack_root / "models", "ModelProfile"),
        runtime_requirements=_discover_yaml_names(
            pack_root / "runtime-requirements", "RuntimeRequirement"
        ),
        evals=_discover_yaml_names(pack_root / "evals", "Eval"),
    )


def load_role(pack: Pack, name: str) -> Role:
    if name not in pack.roles:
        raise PackError(f"Pack `{pack.name}` does not define role `{name}`")

    path = pack.root / "roles" / f"{name}.yaml"
    doc = _read_yaml(path)
    metadata = doc.get("metadata")
    spec = doc.get("spec")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise PackError(f"Role `{name}` requires metadata and spec")

    return Role(
        name=name,
        display_name=str(metadata.get("displayName") or name),
        org=_optional_str(spec.get("org")),
        project=_optional_str(spec.get("project")),
        purpose=str(spec.get("purpose") or ""),
        skills=_as_list(spec.get("skills")),
        runtime_requirements=_as_list(spec.get("runtimeRequirements")),
        model_profile=_optional_str(spec.get("modelProfile")),
        responsibilities=_as_list(spec.get("responsibilities")),
    )


def load_team(pack: Pack, name: str) -> Team:
    if name not in pack.teams:
        raise PackError(f"Pack `{pack.name}` does not define team `{name}`")

    path = pack.root / "teams" / f"{name}.yaml"
    doc = _read_yaml(path)
    metadata = doc.get("metadata")
    spec = doc.get("spec")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise PackError(f"Team `{name}` requires metadata and spec")

    return Team(
        name=name,
        display_name=str(metadata.get("displayName") or name),
        org=_optional_str(spec.get("org")),
        business_unit=_optional_str(spec.get("businessUnit")),
        project=_optional_str(spec.get("project")),
        purpose=str(spec.get("purpose") or ""),
        roles=_as_list(spec.get("roles")),
        default_model_profile=_optional_str(spec.get("defaultModelProfile")),
    )


def validate_pack(pack: Pack) -> None:
    if not pack.skills:
        raise PackError("Pack must define at least one skill")

    for skill in pack.skills:
        _validate_skill(pack.root / "skills" / skill / "SKILL.md", skill)

    for role_name in pack.roles:
        role = load_role(pack, role_name)
        for skill in role.skills:
            if skill not in pack.skills:
                raise PackError(f"Role `{role_name}` references missing skill `{skill}`")
        for requirement in role.runtime_requirements:
            if requirement not in pack.runtime_requirements:
                raise PackError(
                    f"Role `{role_name}` references missing runtime requirement `{requirement}`"
                )
        if role.model_profile and role.model_profile not in pack.model_profiles:
            raise PackError(
                f"Role `{role_name}` references missing model profile `{role.model_profile}`"
            )

    for team_name in pack.teams:
        team = load_team(pack, team_name)
        for role in team.roles:
            if role not in pack.roles:
                raise PackError(f"Team `{team_name}` references missing role `{role}`")
        if team.default_model_profile and team.default_model_profile not in pack.model_profiles:
            raise PackError(
                f"Team `{team_name}` references missing model profile `{team.default_model_profile}`"
            )

    for eval_path in sorted((pack.root / "evals").glob("*.yaml")):
        doc = _read_yaml(eval_path)
        metadata = doc.get("metadata", {})
        eval_name = metadata.get("name", eval_path.stem) if isinstance(metadata, dict) else eval_path.stem
        spec = doc.get("spec")
        if not isinstance(spec, dict) or not spec.get("skill"):
            raise PackError(f"Eval `{eval_name}` spec.skill is required")
        skill = str(spec["skill"])
        if skill not in pack.skills:
            raise PackError(f"Eval `{eval_name}` references missing skill `{skill}`")


def _discover_skills(skills_dir: Path) -> list[str]:
    if not skills_dir.exists():
        return []

    skills: list[str] = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        skills.append(skill_file.parent.name)
    return skills


def _validate_skill(path: Path, expected_name: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise PackError(f"{path} must start with YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise PackError(f"{path} must contain YAML frontmatter")
    frontmatter = yaml.safe_load(parts[1]) or {}
    if not isinstance(frontmatter, dict):
        raise PackError(f"{path} frontmatter must be a YAML object")
    if frontmatter.get("name") != expected_name:
        raise PackError(f"{path} frontmatter name must be `{expected_name}`")
    if not frontmatter.get("description"):
        raise PackError(f"{path} frontmatter description is required")


def _discover_yaml_names(root: Path, expected_kind: str) -> list[str]:
    if not root.exists():
        return []

    names: list[str] = []
    for path in sorted(root.glob("*.yaml")):
        doc = _read_yaml(path)
        if doc.get("kind") != expected_kind:
            raise PackError(f"{path} kind must be {expected_kind}")
        metadata = doc.get("metadata")
        if not isinstance(metadata, dict) or not metadata.get("name"):
            raise PackError(f"{path} metadata.name is required")
        names.append(str(metadata["name"]))
    return names


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PackError(f"Missing required file: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise PackError(f"{path} must contain a YAML object")
    return data


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise PackError(f"Expected list value, got {type(value).__name__}")
    return [str(item) for item in value]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

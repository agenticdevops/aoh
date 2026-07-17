from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aoh.pack import Binding, PackError, load_binding
from aoh.paths import safe_segment

_SITE_API_VERSION = "openagentix.io/v1alpha2"
_USER_CONFIG_API_VERSION = "openagentix.io/v1alpha2"
_SITE_LOCK_API_VERSION = "openagentix.io/v1alpha2"

SITE_LOCK_FILENAME = "site.lock.yaml"


# ---------------------------------------------------------------------------
# PackSource
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PackSource:
    repo: str | None
    subdir: str = ""
    ref: str = "HEAD"
    local_path: Path | None = None


def parse_pack_source(value: Any) -> PackSource:
    """Parse a pack source from either a dict {repo, subdir, ref} or a bare
    string (treated as a local path)."""
    if isinstance(value, str):
        return PackSource(repo=None, subdir="", ref="HEAD", local_path=Path(value))

    if isinstance(value, dict):
        repo = value.get("repo")
        if not repo:
            raise PackError("Pack source dict requires `repo`")
        subdir = _normalize_subdir(str(value.get("subdir", "")))
        ref = str(value.get("ref", "HEAD"))
        return PackSource(repo=str(repo), subdir=subdir, ref=ref, local_path=None)

    raise PackError(f"Pack source must be a string or mapping, got {type(value).__name__}")


def _normalize_subdir(subdir: str) -> str:
    if not subdir:
        return ""
    if subdir.startswith("/"):
        raise PackError(f"Pack source subdir `{subdir}` must not be absolute")
    normalized = posixpath.normpath(subdir)
    if normalized in ("..", ".") or normalized.startswith("../") or normalized.startswith("/"):
        raise PackError(f"Pack source subdir `{subdir}` must not escape the repo root")
    return normalized


# ---------------------------------------------------------------------------
# UserConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UserConfig:
    packs: dict[str, PackSource]
    site: str | None
    registries: dict[str, str]
    default_runtime: str
    default_model: str | None
    workspace_root: Path | None


def load_user_config(aoh_home: Path | None = None) -> UserConfig:
    home = aoh_home if aoh_home is not None else Path.home() / ".aoh"
    config_path = Path(home) / "config.yaml"

    if not config_path.exists():
        return UserConfig(
            packs={},
            site=None,
            registries={},
            default_runtime="claude-code",
            default_model=None,
            workspace_root=None,
        )

    doc = _read_yaml(config_path)

    api_version = doc.get("apiVersion")
    if api_version is not None and api_version != _USER_CONFIG_API_VERSION:
        raise PackError(f"{config_path} apiVersion must be {_USER_CONFIG_API_VERSION}")
    kind = doc.get("kind")
    if kind is not None and kind != "UserConfig":
        raise PackError(f"{config_path} kind must be UserConfig")

    packs_raw = doc.get("packs") or {}
    if not isinstance(packs_raw, dict):
        raise PackError(f"{config_path} packs must be a mapping")
    packs = {str(name): parse_pack_source(value) for name, value in packs_raw.items()}

    site = doc.get("site")
    site = str(site) if site is not None else None

    registries_raw = doc.get("registries") or {}
    if not isinstance(registries_raw, dict):
        raise PackError(f"{config_path} registries must be a mapping")
    registries = {str(k): str(v) for k, v in registries_raw.items()}

    defaults = doc.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise PackError(f"{config_path} defaults must be a mapping")

    default_runtime = str(defaults.get("runtime") or "claude-code")
    default_model_raw = defaults.get("model")
    default_model = str(default_model_raw) if default_model_raw is not None else None

    workspace_root_raw = defaults.get("workspaceRoot")
    workspace_root = Path(workspace_root_raw) if workspace_root_raw else None

    return UserConfig(
        packs=packs,
        site=site,
        registries=registries,
        default_runtime=default_runtime,
        default_model=default_model,
        workspace_root=workspace_root,
    )


# ---------------------------------------------------------------------------
# Site
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteGroup:
    name: str
    vars: dict[str, str]


@dataclass(frozen=True)
class Site:
    root: Path
    name: str
    workspace_root_advisory: Path | None
    defaults: dict[str, str]
    target_defaults: dict[str, str]
    packs: dict[str, PackSource]
    groups: dict[str, SiteGroup]
    bindings: list[Binding]


def load_site(root: Path | str) -> Site:
    site_root = Path(root)
    site_path = site_root / "site.yaml"
    doc = _read_yaml(site_path)

    if doc.get("apiVersion") != _SITE_API_VERSION:
        raise PackError(f"{site_path} apiVersion must be {_SITE_API_VERSION}")
    if doc.get("kind") != "Site":
        raise PackError(f"{site_path} kind must be Site")

    metadata = doc.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("name"):
        raise PackError(f"{site_path} metadata.name is required")
    name = str(metadata["name"])

    spec = doc.get("spec")
    if not isinstance(spec, dict):
        spec = {}

    workspace_root_raw = spec.get("workspaceRoot")
    workspace_root_advisory = Path(workspace_root_raw) if workspace_root_raw else None

    defaults_raw = spec.get("defaults") or {}
    if not isinstance(defaults_raw, dict):
        raise PackError(f"{site_path} spec.defaults must be a mapping")
    defaults: dict[str, str] = {}
    for key in ("runtime", "model"):
        if key in defaults_raw and defaults_raw[key] is not None:
            defaults[key] = str(defaults_raw[key])

    target_defaults_raw = spec.get("targetDefaults") or {}
    if not isinstance(target_defaults_raw, dict):
        raise PackError(f"{site_path} spec.targetDefaults must be a mapping")
    target_defaults = {str(k): str(v) for k, v in target_defaults_raw.items()}

    packs_raw = spec.get("packs") or {}
    if not isinstance(packs_raw, dict):
        raise PackError(f"{site_path} spec.packs must be a mapping")
    packs = {str(pname): parse_pack_source(pvalue) for pname, pvalue in packs_raw.items()}

    groups_raw = spec.get("groups") or {}
    if not isinstance(groups_raw, dict):
        raise PackError(f"{site_path} spec.groups must be a mapping")
    groups: dict[str, SiteGroup] = {}
    for gname, gvalue in groups_raw.items():
        gname_str = str(gname)
        safe_segment("group", gname_str)
        if not isinstance(gvalue, dict):
            raise PackError(f"{site_path} spec.groups.{gname_str} must be a mapping")
        gvars_raw = gvalue.get("vars") or {}
        if not isinstance(gvars_raw, dict):
            raise PackError(f"{site_path} spec.groups.{gname_str}.vars must be a mapping")
        gvars = {str(k): str(v) for k, v in gvars_raw.items()}
        groups[gname_str] = SiteGroup(name=gname_str, vars=gvars)

    bindings_dir_raw = spec.get("bindingsDir")
    bindings = _load_bindings_dir(site_root, bindings_dir_raw, packs, groups)

    return Site(
        root=site_root,
        name=name,
        workspace_root_advisory=workspace_root_advisory,
        defaults=defaults,
        target_defaults=target_defaults,
        packs=packs,
        groups=groups,
        bindings=bindings,
    )


def _load_bindings_dir(
    site_root: Path,
    bindings_dir_raw: Any,
    packs: dict[str, PackSource],
    groups: dict[str, SiteGroup],
) -> list[Binding]:
    if not bindings_dir_raw:
        return []

    bindings_dir = site_root / str(bindings_dir_raw)
    if not bindings_dir.exists():
        return []

    if bindings_dir.is_symlink():
        raise PackError(f"{bindings_dir} must not be a symlink")

    bindings: list[Binding] = []
    seen_names: set[str] = set()
    for path in sorted(bindings_dir.glob("*.yaml")):
        if path.is_symlink():
            raise PackError(f"{path} must not be a symlink")

        binding = load_binding(path)

        safe_segment("binding", binding.name)

        if path.stem != binding.name:
            raise PackError(
                f"{path} filename stem `{path.stem}` must equal metadata.name `{binding.name}`"
            )

        if binding.name in seen_names:
            raise PackError(f"Duplicate binding name `{binding.name}` in {bindings_dir}")
        seen_names.add(binding.name)

        if binding.group is not None and binding.group not in groups:
            raise PackError(
                f"Binding `{binding.name}` references missing group `{binding.group}`"
            )

        if binding.pack is not None:
            if binding.pack not in packs:
                raise PackError(
                    f"Binding `{binding.name}` references missing pack `{binding.pack}`"
                )
        else:
            if len(packs) > 1:
                raise PackError(
                    f"Binding `{binding.name}` does not set spec.pack and site defines "
                    f"multiple packs — ambiguous"
                )

        bindings.append(binding)

    return bindings


# ---------------------------------------------------------------------------
# Precedence resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedBinding:
    binding: Binding
    pack_name: str
    pack_source: PackSource
    runtime: str
    model: str | None
    target: dict[str, str]


def resolve_binding_settings(
    site: Site,
    binding: Binding,
    user: UserConfig,
    cli_runtime: str | None = None,
) -> ResolvedBinding:
    # target: site.target_defaults < group.vars < binding.target
    target: dict[str, str] = dict(site.target_defaults)
    if binding.group is not None:
        group = site.groups.get(binding.group)
        if group is None:
            raise PackError(f"Binding `{binding.name}` references missing group `{binding.group}`")
        target.update(group.vars)
    target.update({str(k): str(v) for k, v in binding.target.items()})

    # runtime: cli > binding.runtime > site.defaults.runtime > user.default_runtime
    runtime = (
        cli_runtime
        or binding.runtime
        or site.defaults.get("runtime")
        or user.default_runtime
    )

    # model: site.defaults.model > user.default_model
    model = site.defaults.get("model") or user.default_model

    # pack resolution: binding.pack > sole site pack > error if ambiguous
    if binding.pack is not None:
        pack_name = binding.pack
    elif len(site.packs) == 1:
        pack_name = next(iter(site.packs))
    else:
        raise PackError(
            f"Binding `{binding.name}` does not set spec.pack and site defines "
            f"multiple packs — ambiguous"
        )

    if pack_name not in site.packs:
        raise PackError(f"Binding `{binding.name}` references missing pack `{pack_name}`")
    pack_source = site.packs[pack_name]

    return ResolvedBinding(
        binding=binding,
        pack_name=pack_name,
        pack_source=pack_source,
        runtime=runtime,
        model=model,
        target=target,
    )


# ---------------------------------------------------------------------------
# SiteLock — minimal Phase A lock (F1 subset)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LockedPack:
    repo: str | None
    subdir: str
    requested_ref: str
    resolved_commit: str | None
    local: bool = False
    local_path: Path | None = None


@dataclass(frozen=True)
class SiteLock:
    root: Path
    packs: dict[str, LockedPack]


def load_site_lock(root: Path | str) -> SiteLock | None:
    """Load `site.lock.yaml` beside `site.yaml`. Returns None if the lock
    file does not exist yet (a site with no lock)."""
    site_root = Path(root)
    lock_path = site_root / SITE_LOCK_FILENAME
    if not lock_path.exists():
        return None

    doc = _read_yaml(lock_path)

    if doc.get("apiVersion") != _SITE_LOCK_API_VERSION:
        raise PackError(f"{lock_path} apiVersion must be {_SITE_LOCK_API_VERSION}")
    if doc.get("kind") != "SiteLock":
        raise PackError(f"{lock_path} kind must be SiteLock")

    packs_raw = doc.get("packs") or {}
    if not isinstance(packs_raw, dict):
        raise PackError(f"{lock_path} packs must be a mapping")

    packs: dict[str, LockedPack] = {}
    for name, value in packs_raw.items():
        pname = str(name)
        if not isinstance(value, dict):
            raise PackError(f"{lock_path} packs.{pname} must be a mapping")

        local = bool(value.get("local", False))
        if local:
            path_raw = value.get("path")
            if not path_raw:
                raise PackError(f"{lock_path} packs.{pname} local entry requires `path`")
            packs[pname] = LockedPack(
                repo=None,
                subdir="",
                requested_ref="HEAD",
                resolved_commit=None,
                local=True,
                local_path=Path(str(path_raw)),
            )
            continue

        repo = value.get("repo")
        if not repo:
            raise PackError(f"{lock_path} packs.{pname} requires `repo` (or `local: true`)")
        subdir = str(value.get("subdir", ""))
        requested_ref = str(value.get("requestedRef", "HEAD"))
        resolved_commit_raw = value.get("resolvedCommit")
        resolved_commit = str(resolved_commit_raw) if resolved_commit_raw else None
        packs[pname] = LockedPack(
            repo=str(repo),
            subdir=subdir,
            requested_ref=requested_ref,
            resolved_commit=resolved_commit,
            local=False,
            local_path=None,
        )

    return SiteLock(root=site_root, packs=packs)


def write_site_lock(root: Path | str, lock: SiteLock) -> Path:
    """Write `site.lock.yaml` beside `site.yaml`, camelCase keys."""
    site_root = Path(root)
    lock_path = site_root / SITE_LOCK_FILENAME

    packs_doc: dict[str, Any] = {}
    for name, entry in lock.packs.items():
        if entry.local:
            packs_doc[name] = {
                "local": True,
                "path": str(entry.local_path) if entry.local_path is not None else None,
            }
        else:
            packs_doc[name] = {
                "repo": entry.repo,
                "subdir": entry.subdir,
                "requestedRef": entry.requested_ref,
                "resolvedCommit": entry.resolved_commit,
            }

    doc = {
        "apiVersion": _SITE_LOCK_API_VERSION,
        "kind": "SiteLock",
        "packs": packs_doc,
    }

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(doc, handle, sort_keys=False)

    return lock_path


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PackError(f"Missing required file: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise PackError(f"{path} must contain a YAML object")
    return data

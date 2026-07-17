from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

import aoh.adapters
from aoh.adapters.base import ADAPTERS, AdapterResult, MaterializeRequest
from aoh.adapters.hermes import (
    generate_hermes_adapter,
    install_hermes_agent,
    install_hermes_pack,
    install_hermes_team,
)
from aoh.authoring import create_pack
from aoh.gitops import GitOpsError, ensure_mirror, resolve_commit, source_checkout
from aoh.installer import InstallRefused, install_workspace
from aoh.manifest import NAMING_SCHEME_LEGACY, NAMING_SCHEME_SITE_QUALIFIED, read_manifest
from aoh.pack import PackError, load_binding, load_pack, validate_pack
from aoh.site import (
    LockedPack,
    PackSource,
    Site,
    SiteLock,
    UserConfig,
    load_site,
    load_site_lock,
    load_user_config,
    resolve_binding_settings,
    write_site_lock,
)


def _aoh_home() -> Path:
    """Resolve AOH_HOME: env var if set, else ~/.aoh. Every command touching
    config/cache/exports goes through this (F13)."""
    raw = os.environ.get("AOH_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".aoh"


def _cache_dir(aoh_home: Path) -> Path:
    return aoh_home / "cache"


class _LegacyHermesAgentAdapter:
    """Adapts the legacy `install_hermes_agent(profiles_dir=..., category=...)`
    call — which the exact-dir HermesAdapter cannot fully express (it hides
    `category` behind the default) — into the `RuntimeAdapter` protocol so
    `install-hermes-agent` can route through `install_workspace` (F2) while
    keeping `install_hermes_agent`'s own signature/behavior untouched.
    """

    name = "hermes"

    def __init__(self, *, provider: str, model: str, cwd: str, category: str):
        self.provider = provider
        self.model = model
        self.cwd = cwd
        self.category = category

    def materialize(self, request: MaterializeRequest) -> AdapterResult:
        output_dir = Path(request.output_dir)
        result = install_hermes_agent(
            request.pack,
            output_dir.parent,
            profile_name=output_dir.name,
            provider=self.provider,
            model=self.model,
            cwd=self.cwd,
            category=self.category,
            role_name=request.role_name,
            binding=request.binding,
        )
        generated_files = sorted(p for p in output_dir.rglob("*") if p.is_file())
        return AdapterResult(
            runtime="hermes",
            output_dir=output_dir,
            generated_files=generated_files,
            diagnostics=result.diagnostics,
        )


# ---------------------------------------------------------------------------
# aoh lock
# ---------------------------------------------------------------------------


def _pack_source_matches_lock(pack_source: PackSource, locked: LockedPack) -> bool:
    if pack_source.local_path is not None:
        return locked.local and locked.local_path == Path(pack_source.local_path)
    return (
        not locked.local
        and locked.repo == pack_source.repo
        and locked.subdir == pack_source.subdir
        and locked.requested_ref == pack_source.ref
    )


def _cmd_lock(args: argparse.Namespace) -> int:
    try:
        site = load_site(args.site)
    except PackError as exc:
        print(f"invalid AOH site: {exc}", file=sys.stderr)
        return 1

    existing = load_site_lock(site.root)
    existing_packs = dict(existing.packs) if existing is not None else {}

    update_scope = args.update  # None | "__all__" | "<pack-name>"
    cache_dir = _cache_dir(_aoh_home())

    new_packs: dict[str, LockedPack] = dict(existing_packs)
    changed: list[str] = []
    blocked: list[str] = []

    for name, source in site.packs.items():
        current = existing_packs.get(name)
        pack_wants_update = update_scope is not None and update_scope in ("__all__", name)

        if current is not None and not pack_wants_update:
            # Lock initializes only — never touches an existing entry.
            if not _pack_source_matches_lock(source, current):
                blocked.append(
                    f"  {name}: site.yaml source/ref differs from the lock "
                    f"(run `aoh lock --site {site.root} --update {name}` to move it)"
                )
            continue

        if current is not None and pack_wants_update:
            source_changed = not _pack_source_matches_lock(source, current)
            if source_changed and not args.yes:
                blocked.append(
                    f"  {name}: lock update changes source/ref — pass --yes to confirm "
                    f"(old: repo={current.repo} subdir={current.subdir} ref={current.requested_ref}"
                    f"{' local' if current.local else ''})"
                )
                continue

        if source.local_path is not None:
            resolved_path = Path(source.local_path)
            if not resolved_path.exists():
                blocked.append(f"  {name}: local pack source `{resolved_path}` does not exist")
                continue
            new_entry = LockedPack(
                repo=None,
                subdir="",
                requested_ref="HEAD",
                resolved_commit=None,
                local=True,
                local_path=resolved_path,
            )
        else:
            try:
                mirror = ensure_mirror(cache_dir, source.repo)
                commit = resolve_commit(mirror, source.ref)
            except GitOpsError as exc:
                blocked.append(f"  {name}: {exc}")
                continue
            new_entry = LockedPack(
                repo=source.repo,
                subdir=source.subdir,
                requested_ref=source.ref,
                resolved_commit=commit,
                local=False,
                local_path=None,
            )

        old_commit = current.resolved_commit if current is not None else None
        if current is not None and pack_wants_update:
            if old_commit != new_entry.resolved_commit or current != new_entry:
                changed.append(f"  {name}: {old_commit} -> {new_entry.resolved_commit}")
        new_packs[name] = new_entry

    if blocked:
        print("aoh lock: refusing to update the following packs without confirmation:", file=sys.stderr)
        for line in blocked:
            print(line, file=sys.stderr)
        return 1

    write_site_lock(site.root, SiteLock(root=site.root, packs=new_packs))

    for line in changed:
        print(line)
    print(f"wrote {site.root / 'site.lock.yaml'}")
    return 0


# ---------------------------------------------------------------------------
# aoh install --site — fan-out
# ---------------------------------------------------------------------------


def _effective_workspace_root(args: argparse.Namespace, site: Site, user: UserConfig) -> Path:
    if args.workspace_root is not None:
        print(f"workspace root: using --workspace-root ({args.workspace_root})", file=sys.stderr)
        return Path(args.workspace_root).expanduser()

    if user.workspace_root is not None:
        print(f"workspace root: using configured user.workspaceRoot ({user.workspace_root})", file=sys.stderr)
        return Path(user.workspace_root).expanduser()

    if args.accept_site_root and site.workspace_root_advisory is not None:
        advisory = Path(site.workspace_root_advisory).expanduser()
        print(f"workspace root: using site advisory ({advisory}, --accept-site-root)", file=sys.stderr)
        return advisory

    if site.workspace_root_advisory is not None and not args.accept_site_root:
        print(
            f"workspace root: IGNORING site advisory ({site.workspace_root_advisory}) — "
            "pass --accept-site-root to use it; falling back to ~/agents",
            file=sys.stderr,
        )

    default_root = Path.home() / "agents"
    print(f"workspace root: using default (~/agents = {default_root})", file=sys.stderr)
    return default_root


def _cmd_install_site(args: argparse.Namespace) -> int:
    try:
        site = load_site(args.site)
    except PackError as exc:
        print(f"invalid AOH site: {exc}", file=sys.stderr)
        return 1

    lock = load_site_lock(site.root)
    if lock is None:
        print(
            f"no site.lock.yaml found at {site.root} — run `aoh lock --site {site.root}` first",
            file=sys.stderr,
        )
        return 1

    for name, source in site.packs.items():
        locked = lock.packs.get(name)
        if locked is None:
            print(
                f"pack `{name}` is not in the lock — run `aoh lock --site {site.root}` first",
                file=sys.stderr,
            )
            return 1
        if not _pack_source_matches_lock(source, locked):
            print(
                f"site.yaml and site.lock.yaml disagree on pack `{name}`'s source/ref — "
                f"run `aoh lock --site {site.root} --update {name}`",
                file=sys.stderr,
            )
            return 1

    user = load_user_config(_aoh_home())
    workspace_root = _effective_workspace_root(args, site, user)
    cache_dir = _cache_dir(_aoh_home())

    bindings = site.bindings
    if args.binding:
        bindings = [b for b in bindings if b.name == args.binding]
        if not bindings:
            print(f"no binding named `{args.binding}` in site {site.root}", file=sys.stderr)
            return 1
    if args.group:
        bindings = [b for b in bindings if b.group == args.group]
        if not bindings:
            print(f"no binding in group `{args.group}` in site {site.root}", file=sys.stderr)
            return 1

    if not bindings:
        print(f"site {site.root} has no bindings to install", file=sys.stderr)
        return 0

    failures: list[str] = []
    installed: list[str] = []

    for binding in bindings:
        try:
            resolved = resolve_binding_settings(site, binding, user, cli_runtime=args.runtime)
            locked_pack = lock.packs[resolved.pack_name]

            if locked_pack.local:
                checkout_source = PackSource(repo=None, local_path=locked_pack.local_path)
                commit = None
                source_dict: dict[str, Any] = {"local": True, "path": str(locked_pack.local_path)}
            else:
                # Pin to the LOCKED commit as the `ref` — source_checkout
                # resolves whatever ref it's given, so passing the already-
                # resolved sha means it never re-resolves a movable branch
                # (F1: the lock, not site.yaml, decides what gets installed).
                checkout_source = PackSource(
                    repo=locked_pack.repo,
                    subdir=locked_pack.subdir,
                    ref=locked_pack.resolved_commit,
                )
                commit = locked_pack.resolved_commit
                source_dict = {
                    "repo": locked_pack.repo,
                    "subdir": locked_pack.subdir,
                    "ref": locked_pack.requested_ref,
                }

            pack_path, _origin = source_checkout(checkout_source, cache_dir)

            pack = load_pack(pack_path)
            validate_pack(pack)

            # Adapters read `binding.target` directly (not the
            # precedence-merged ResolvedBinding.target), so attach a
            # synthetic Binding carrying the fully-resolved target.
            merged_binding = dataclasses.replace(binding, target=resolved.target)

            workspace = workspace_root / binding.name
            req = MaterializeRequest(
                pack=pack,
                output_dir=workspace,
                role_name=binding.role,
                binding=merged_binding,
                model_hint=resolved.model,
                options={"site_name": site.name},
            )

            result = install_workspace(
                adapter=ADAPTERS[resolved.runtime],
                request=req,
                source=source_dict,
                commit=commit,
                naming_scheme=NAMING_SCHEME_SITE_QUALIFIED,
                discard_local=args.discard_local,
                binding_name=binding.name,
            )
            for diagnostic in result.diagnostics:
                print(f"warning: {binding.name}: {diagnostic}", file=sys.stderr)
            print(f"installed {binding.name} ({resolved.runtime}) -> {result.output_dir}")
            installed.append(binding.name)
        except (PackError, GitOpsError, InstallRefused) as exc:
            print(f"failed: {binding.name}: {exc}", file=sys.stderr)
            failures.append(binding.name)

    print(f"summary: {len(installed)} installed, {len(failures)} failed")
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# aoh list
# ---------------------------------------------------------------------------


def _credential_state(workspace: Path) -> str:
    provision_json = workspace / "aoh-provision.json"
    if not provision_json.exists():
        return "-"
    try:
        doc = json.loads(provision_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "-"
    expires_raw = doc.get("tokenExpiresAt")
    if not expires_raw:
        return "-"
    try:
        expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
    except ValueError:
        return "-"
    now = datetime.now(timezone.utc)
    return "ok" if expires_at > now else "expired"


def _provisioned_state(workspace: Path) -> str:
    if (workspace / "kubeconfig").exists() or (workspace / "kubeconfig-overlay").exists():
        return "yes"
    return "no"


def _cmd_list(args: argparse.Namespace) -> int:
    user = load_user_config(_aoh_home())

    site_arg = args.site if args.site is not None else user.site
    if site_arg is None:
        print(
            "no site specified: pass --site or set `site` in the user config "
            "(`aoh config set site <path>`)",
            file=sys.stderr,
        )
        return 1

    try:
        site = load_site(site_arg)
    except PackError as exc:
        print(f"invalid AOH site: {exc}", file=sys.stderr)
        return 1

    workspace_root = (
        Path(args.workspace_root).expanduser()
        if getattr(args, "workspace_root", None) is not None
        else (Path(user.workspace_root).expanduser() if user.workspace_root is not None else Path.home() / "agents")
    )

    columns = [
        "BINDING", "ROLE", "PACK@REF", "RUNTIME", "CONTEXT/NS", "ACCESS",
        "WORKSPACE", "PROVISIONED", "CREDENTIAL",
    ]
    rows: list[list[str]] = []
    for binding in site.bindings:
        try:
            resolved = resolve_binding_settings(site, binding, user)
            pack_ref = f"{resolved.pack_name}@{resolved.pack_source.ref}"
        except PackError:
            pack_ref = "?"
            resolved = None

        workspace = workspace_root / binding.name
        manifest = read_manifest(workspace) if workspace.exists() else None
        context_ns = f"{binding.target.get('kubeContext', '-')}/{binding.target.get('namespace', '-')}"
        rows.append(
            [
                binding.name,
                binding.role,
                pack_ref,
                (manifest or {}).get("runtime") or (resolved.runtime if resolved else "-"),
                context_ns,
                binding.access,
                str(workspace) if workspace.exists() else "-",
                _provisioned_state(workspace),
                _credential_state(workspace),
            ]
        )

    _print_table(columns, rows)
    return 0


def _print_table(columns: list[str], rows: list[list[str]]) -> None:
    widths = [len(c) for c in columns]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    header = "  ".join(c.ljust(widths[i]) for i, c in enumerate(columns))
    print(header)
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


# ---------------------------------------------------------------------------
# aoh config
# ---------------------------------------------------------------------------


_USER_CONFIG_API_VERSION = "openagentix.io/v1alpha2"


def _config_path(aoh_home: Path) -> Path:
    return aoh_home / "config.yaml"


def _load_config_doc(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {"apiVersion": _USER_CONFIG_API_VERSION, "kind": "UserConfig"}
    with config_path.open("r", encoding="utf-8") as handle:
        doc = yaml.safe_load(handle) or {}
    if not isinstance(doc, dict):
        raise PackError(f"{config_path} must contain a YAML object")
    return doc


def _write_config_doc(config_path: Path, doc: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(doc, handle, sort_keys=False)


def _get_dotted(doc: dict[str, Any], dotted_key: str) -> Any:
    node: Any = doc
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_dotted(doc: dict[str, Any], dotted_key: str, value: str) -> None:
    parts = dotted_key.split(".")
    node = doc
    for part in parts[:-1]:
        existing = node.get(part)
        if not isinstance(existing, dict):
            existing = {}
            node[part] = existing
        node = existing
    node[parts[-1]] = value


def _cmd_config(args: argparse.Namespace) -> int:
    aoh_home = _aoh_home()
    config_path = _config_path(aoh_home)

    if args.config_action == "init":
        doc = _load_config_doc(config_path)
        doc.setdefault("apiVersion", _USER_CONFIG_API_VERSION)
        doc.setdefault("kind", "UserConfig")
        _write_config_doc(config_path, doc)
        print(f"wrote {config_path}")
        return 0

    if args.config_action == "get":
        try:
            doc = _load_config_doc(config_path)
        except PackError as exc:
            print(f"invalid config: {exc}", file=sys.stderr)
            return 1
        value = _get_dotted(doc, args.key)
        print(value if value is not None else "(unset)")
        return 0

    if args.config_action == "set":
        try:
            doc = _load_config_doc(config_path)
        except PackError as exc:
            print(f"invalid config: {exc}", file=sys.stderr)
            return 1
        doc.setdefault("apiVersion", _USER_CONFIG_API_VERSION)
        doc.setdefault("kind", "UserConfig")
        _set_dotted(doc, args.key, args.value)
        _write_config_doc(config_path, doc)
        print(f"set {args.key} = {args.value}")
        return 0

    print(f"unknown config action: {args.config_action}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aoh")
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate = subcommands.add_parser("validate", help="Validate an AOH pack")
    validate.add_argument("pack", type=Path)

    init_pack = subcommands.add_parser("init-pack", help="Create a starter AOH pack")
    init_pack.add_argument("name")
    init_pack.add_argument("--output", type=Path, required=True)
    init_pack.add_argument("--description", required=True)

    install = subcommands.add_parser(
        "install", help="Install an AOH pack for a runtime (hermes, claude-code, codex)"
    )
    # `install` has two mutually exclusive modes (F10):
    #   legacy: positional pack + --runtime + --output; --binding = FILE PATH
    #   site:   --site (no positional pack); --binding = binding NAME
    # argparse can't express positional-vs-optional exclusivity directly, so
    # `pack` is optional here and exclusivity is enforced in main() before
    # any pack loading happens.
    install.add_argument("pack", type=Path, nargs="?", default=None)
    install.add_argument(
        "--runtime",
        choices=["hermes", "claude-code", "codex"],
        help="Target runtime (legacy mode)",
    )
    install.add_argument("--output", type=Path, help="Output directory (legacy mode)")
    install.add_argument("--binding", help="Binding file path (legacy) or binding name (--site)")
    install.add_argument("--role", help="Role name")
    install.add_argument("--profile", help="Profile name")
    install.add_argument("--model", help="Model hint")
    install.add_argument(
        "--discard-local",
        action="store_true",
        help="Overwrite locally modified owned files instead of refusing to install",
    )
    install.add_argument("--site", type=Path, help="Site root directory (site fan-out mode)")
    install.add_argument("--group", help="Only install bindings in this group (site mode)")
    install.add_argument(
        "--workspace-root", type=Path, help="Explicit workspace root (site mode)"
    )
    install.add_argument(
        "--accept-site-root",
        action="store_true",
        help="Use the site's workspaceRoot advisory if no --workspace-root/user default is set",
    )

    list_cmd = subcommands.add_parser("list", help="List fleet workspaces for a site")
    list_cmd.add_argument("--site", type=Path, help="Site root directory")
    list_cmd.add_argument(
        "--workspace-root", type=Path, help="Workspace root to inspect (site mode)"
    )

    config_cmd = subcommands.add_parser("config", help="Manage the AOH user config")
    config_sub = config_cmd.add_subparsers(dest="config_action", required=True)
    config_sub.add_parser("init", help="Create a starter user config")
    config_get = config_sub.add_parser("get", help="Read a dotted config key")
    config_get.add_argument("key")
    config_set = config_sub.add_parser("set", help="Write a dotted config key")
    config_set.add_argument("key")
    config_set.add_argument("value")

    lock_cmd = subcommands.add_parser("lock", help="Resolve and pin site pack refs to commits")
    lock_cmd.add_argument("--site", type=Path, default=Path("."), help="Site root directory")
    lock_cmd.add_argument(
        "--update", nargs="?", const="__all__", default=None, metavar="PACK",
        help="Move locked entries to their current ref (optionally scoped to one pack)",
    )
    lock_cmd.add_argument("--yes", action="store_true", help="Confirm source/ref changes non-interactively")

    hermes = subcommands.add_parser("adapt-hermes", help="Generate a Hermes-native view")
    hermes.add_argument("pack", type=Path)
    hermes.add_argument("--output", type=Path, required=True)

    install_hermes = subcommands.add_parser(
        "install-hermes", help="Install AOH pack skills into a Hermes skills directory"
    )
    install_hermes.add_argument("pack", type=Path)
    install_hermes.add_argument("--skills-dir", type=Path, required=True)
    install_hermes.add_argument("--category", default="aoh")

    agent_hermes = subcommands.add_parser(
        "install-hermes-agent", help="Create a launchable Hermes profile for an AOH pack"
    )
    agent_hermes.add_argument("pack", type=Path)
    agent_hermes.add_argument("--profiles-dir", type=Path, default=Path("~/.hermes/profiles"))
    agent_hermes.add_argument("--profile", required=True)
    agent_hermes.add_argument("--provider", default="openai-codex")
    agent_hermes.add_argument("--model", default="gpt-5.4")
    agent_hermes.add_argument("--cwd", default=str(Path.cwd()))
    agent_hermes.add_argument("--category", default="aoh")
    agent_hermes.add_argument("--role")
    agent_hermes.add_argument("--binding", type=Path)

    team_hermes = subcommands.add_parser(
        "install-hermes-team", help="Create Hermes profiles for every role in an AOH team"
    )
    team_hermes.add_argument("pack", type=Path)
    team_hermes.add_argument("--profiles-dir", type=Path, default=Path("~/.hermes/profiles"))
    team_hermes.add_argument("--team", required=True)
    team_hermes.add_argument("--profile-prefix", required=True)
    team_hermes.add_argument("--provider", default="openai-codex")
    team_hermes.add_argument("--model", default="gpt-5.4")
    team_hermes.add_argument("--cwd", default=str(Path.cwd()))
    team_hermes.add_argument("--category", default="aoh")

    args = parser.parse_args(argv)

    # F10: `list`/`config`/`lock` dispatch BEFORE any pack loading — none of
    # them touch a Pack. `install` mode exclusivity is also checked here,
    # before `args.pack` is ever passed to `load_pack`.
    if args.command == "list":
        return _cmd_list(args)
    if args.command == "config":
        return _cmd_config(args)
    if args.command == "lock":
        return _cmd_lock(args)

    if args.command == "install":
        site_mode = args.site is not None
        legacy_mode = args.pack is not None or args.runtime is not None or args.output is not None
        if site_mode and legacy_mode:
            parser.error("install: --site cannot be combined with a positional pack, --runtime, or --output")
        if not site_mode and not legacy_mode:
            parser.error("install: either a positional pack (with --runtime/--output) or --site is required")
        if not site_mode:
            if args.pack is None:
                parser.error("install: the positional pack argument is required in legacy mode")
            if args.runtime is None:
                parser.error("install: --runtime is required in legacy mode")
            if args.output is None:
                parser.error("install: --output is required in legacy mode")

    try:
        if args.command == "init-pack":
            target = create_pack(args.name, args.output, args.description)
            print(f"created AOH pack: {target}")
            return 0

        if args.command == "install" and args.site is not None:
            return _cmd_install_site(args)

        pack = load_pack(args.pack)
        if args.command == "validate":
            validate_pack(pack)
            print(f"valid AOH pack: {pack.name}")
            return 0
        if args.command == "install":
            validate_pack(pack)
            binding = load_binding(Path(args.binding)) if args.binding else None
            output_dir = args.output
            if args.runtime == "hermes":
                # The adapter contract is exact-dir (materialize writes into
                # EXACTLY request.output_dir — v0.3 A3 / F9). The Hermes CLI
                # path historically nested output under
                # `<output>/<profile>/`; that printed/observed layout is
                # preserved here, in the CLI handler, by computing the final
                # directory BEFORE calling materialize — the adapter itself
                # no longer knows about this nesting.
                profile_name = args.profile or (binding.name if binding else pack.name)
                output_dir = args.output / profile_name
            req = MaterializeRequest(
                pack=pack,
                output_dir=output_dir,
                role_name=args.role,
                binding=binding,
                profile=args.profile,
                model_hint=args.model,
            )
            try:
                result = install_workspace(
                    adapter=ADAPTERS[args.runtime],
                    request=req,
                    source={"repo": None, "subdir": "", "ref": "HEAD"},
                    commit=None,
                    naming_scheme=NAMING_SCHEME_LEGACY,
                    discard_local=args.discard_local,
                )
            except InstallRefused as exc:
                print(f"install refused: {exc}", file=sys.stderr)
                return 1
            for diagnostic in result.diagnostics:
                print(f"warning: {diagnostic}", file=sys.stderr)
            print(f"installed {args.runtime} workspace in {result.output_dir}")
            return 0
        if args.command == "adapt-hermes":
            validate_pack(pack)
            result = generate_hermes_adapter(pack, args.output)
            print(f"generated {len(result.generated_files)} Hermes files in {result.output_dir}")
            return 0
        if args.command == "install-hermes":
            validate_pack(pack)
            result = install_hermes_pack(pack, args.skills_dir, category=args.category)
            print(f"installed {len(result.generated_files)} Hermes files in {result.output_dir}")
            return 0
        if args.command == "install-hermes-agent":
            validate_pack(pack)
            binding = load_binding(args.binding) if args.binding else None
            output_dir = Path(args.profiles_dir).expanduser() / args.profile
            req = MaterializeRequest(
                pack=pack,
                output_dir=output_dir,
                role_name=args.role,
                binding=binding,
            )
            adapter = _LegacyHermesAgentAdapter(
                provider=args.provider, model=args.model, cwd=args.cwd, category=args.category
            )
            try:
                result = install_workspace(
                    adapter=adapter,
                    request=req,
                    source={"repo": None, "subdir": "", "ref": "HEAD"},
                    commit=None,
                    naming_scheme=NAMING_SCHEME_LEGACY,
                )
            except InstallRefused as exc:
                print(f"install refused: {exc}", file=sys.stderr)
                return 1
            print(f"installed Hermes agent profile in {result.output_dir}")
            print("hint: prefer 'aoh install --runtime hermes'", file=sys.stderr)
            return 0
        if args.command == "install-hermes-team":
            validate_pack(pack)
            result = install_hermes_team(
                pack,
                args.profiles_dir,
                team_name=args.team,
                profile_prefix=args.profile_prefix,
                provider=args.provider,
                model=args.model,
                cwd=args.cwd,
                category=args.category,
            )
            print(f"installed Hermes team profiles in {result.output_dir}")
            return 0
    except PackError as exc:
        print(f"invalid AOH pack: {exc}")
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import aoh.adapters
from aoh.adapters.base import ADAPTERS, AdapterResult, MaterializeRequest
from aoh.adapters.hermes import (
    generate_hermes_adapter,
    install_hermes_agent,
    install_hermes_pack,
    install_hermes_team,
)
from aoh.authoring import create_pack
from aoh.installer import InstallRefused, install_workspace
from aoh.manifest import NAMING_SCHEME_LEGACY
from aoh.pack import PackError, load_binding, load_pack, validate_pack


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
    install.add_argument("pack", type=Path)
    install.add_argument(
        "--runtime",
        required=True,
        choices=["hermes", "claude-code", "codex"],
        help="Target runtime",
    )
    install.add_argument("--output", type=Path, required=True, help="Output directory")
    install.add_argument("--binding", type=Path, help="Optional binding file")
    install.add_argument("--role", help="Role name")
    install.add_argument("--profile", help="Profile name")
    install.add_argument("--model", help="Model hint")
    install.add_argument(
        "--discard-local",
        action="store_true",
        help="Overwrite locally modified owned files instead of refusing to install",
    )

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

    try:
        if args.command == "init-pack":
            target = create_pack(args.name, args.output, args.description)
            print(f"created AOH pack: {target}")
            return 0

        pack = load_pack(args.pack)
        if args.command == "validate":
            validate_pack(pack)
            print(f"valid AOH pack: {pack.name}")
            return 0
        if args.command == "install":
            validate_pack(pack)
            binding = load_binding(args.binding) if args.binding else None
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
